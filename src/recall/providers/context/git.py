"""Git context source for enhancing session insights with relevant development activity."""

import json
import subprocess
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from recall.context import ContextSource
from recall.models import SessionInsights, ContextMatch
from recall.config import Settings
from recall.logging import debug, error


class GitContextSource(ContextSource):
    """Context source that finds relevant git commits and activity to enhance session insights."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.workspace_path = settings.resolved_workspace_path
        self._repo_cache: List[Path] = []
        self._last_repo_scan: Optional[datetime] = None

    @property
    def source_type(self) -> str:
        return "git"

    async def is_available(self) -> bool:
        """Check if workspace exists and contains git repositories."""
        if not self.workspace_path.exists():
            return False

        repos = await self._discover_repos()
        return len(repos) > 0

    async def find_relevant_content(self, insights: SessionInsights,
                                   session_context: Dict[str, Any]) -> List[ContextMatch]:
        """Find git commits and activity relevant to the session insights."""

        if not await self.is_available():
            debug("Git workspace not available")
            return []

        try:
            # Get search parameters
            search_params = self._extract_search_params(insights, session_context)
            if not search_params:
                debug("No search parameters extracted from insights")
                return []

            repos = await self._discover_repos()
            if not repos:
                debug("No git repositories found")
                return []

            # Find relevant commits across all repos
            context_matches = []

            for repo_path in repos:
                repo_matches = await self._find_repo_context(
                    repo_path, search_params, insights, session_context
                )
                context_matches.extend(repo_matches)

            # Sort by relevance score
            context_matches.sort(key=lambda x: x.relevance_score, reverse=True)

            debug(f"Found {len(context_matches)} relevant git contexts")
            return context_matches

        except Exception as e:
            error(f"Failed to find relevant git content: {e}")
            return []

    async def _discover_repos(self) -> List[Path]:
        """Discover git repositories in the workspace."""

        # Cache repo discovery for 10 minutes
        if (self._last_repo_scan and
            datetime.now(timezone.utc) - self._last_repo_scan < timedelta(minutes=10)):
            return self._repo_cache

        debug("Discovering git repositories")
        repos = []

        if not self.workspace_path.exists():
            return repos

        # Look for .git directories up to 2 levels deep
        for entry in self.workspace_path.iterdir():
            if entry.is_dir():
                if (entry / ".git").exists():
                    repos.append(entry)
                else:
                    # Check one level deeper
                    try:
                        for subentry in entry.iterdir():
                            if subentry.is_dir() and (subentry / ".git").exists():
                                repos.append(subentry)
                    except PermissionError:
                        continue

        self._repo_cache = repos
        self._last_repo_scan = datetime.now(timezone.utc)
        debug(f"Discovered {len(repos)} git repositories")
        return repos

    def _extract_search_params(self, insights: SessionInsights,
                              session_context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract search parameters from insights and session context."""

        params = {
            "keywords": [],
            "file_patterns": [],
            "time_range": None,
            "topics": []
        }

        # Extract keywords from insights
        for insight in insights.insights:
            # Extract technical terms and file-like words
            words = insight.content.lower().split()
            for word in words:
                if (len(word) > 3 and
                    (word.endswith('.py') or word.endswith('.js') or word.endswith('.ts') or
                     word.endswith('.md') or word.endswith('.json') or word.endswith('.yaml') or
                     word in ['config', 'setup', 'install', 'deploy', 'build', 'test', 'fix', 'add', 'update'])):
                    params["keywords"].append(word)

        # Extract from session context
        if "files_touched" in session_context:
            files = session_context["files_touched"]
            for file_path in files:
                if file_path:
                    path_obj = Path(file_path)
                    params["file_patterns"].append(path_obj.name)
                    if path_obj.suffix:
                        params["file_patterns"].append(f"*{path_obj.suffix}")

        if "session_date" in session_context:
            # Look for commits in the last 7 days from session date
            session_date = session_context["session_date"]
            params["time_range"] = {
                "start": session_date - timedelta(days=7),
                "end": session_date + timedelta(days=1)
            }

        # Add primary theme as a keyword
        if insights.primary_theme:
            params["keywords"].append(insights.primary_theme.lower())

        return params

    async def _find_repo_context(self, repo_path: Path, search_params: Dict[str, Any],
                                insights: SessionInsights, session_context: Dict[str, Any]) -> List[ContextMatch]:
        """Find relevant context from a specific repository."""

        context_matches = []

        try:
            # Find recent commits
            commits = await self._get_recent_commits(repo_path, search_params.get("time_range"))

            # Find commits that match file patterns
            file_commits = await self._get_commits_by_files(repo_path, search_params.get("file_patterns", []))

            # Find commits that match keywords
            keyword_commits = await self._get_commits_by_keywords(repo_path, search_params.get("keywords", []))

            # Combine and deduplicate commits
            all_commits = {}
            for commit_list in [commits, file_commits, keyword_commits]:
                for commit in commit_list:
                    all_commits[commit["sha"]] = commit

            # Create context matches
            for commit in all_commits.values():
                relevance_score, match_reasons = self._calculate_commit_relevance(
                    commit, search_params, insights
                )

                if relevance_score > 0:
                    context_matches.append(ContextMatch(
                        source_type=self.source_type,
                        content=self._format_commit_content(commit, repo_path),
                        relevance_score=relevance_score,
                        match_reasons=match_reasons,
                        metadata={
                            "sha": commit["sha"],
                            "repo": repo_path.name,
                            "author": commit.get("author", "unknown"),
                            "date": commit.get("date", ""),
                            "repo_path": str(repo_path)
                        }
                    ))

        except Exception as e:
            debug(f"Failed to get context from repo {repo_path}: {e}")

        return context_matches

    async def _get_recent_commits(self, repo_path: Path, time_range: Optional[Dict] = None) -> List[Dict]:
        """Get recent commits from a repository."""

        if time_range:
            since = time_range["start"].strftime('%Y-%m-%d %H:%M:%S')
            until = time_range["end"].strftime('%Y-%m-%d %H:%M:%S')
            time_args = [f"--since={since}", f"--until={until}"]
        else:
            # Default to last 30 days
            time_args = ["--since=30 days ago"]

        cmd = [
            "git", "-C", str(repo_path), "log",
            "--pretty=format:{\"sha\":\"%h\",\"message\":\"%s\",\"date\":\"%ad\",\"author\":\"%an\"}",
            "--date=iso",
            "--max-count=50"  # Limit to 50 recent commits
        ] + time_args

        return await self._run_git_command(cmd, repo_path)

    async def _get_commits_by_files(self, repo_path: Path, file_patterns: List[str]) -> List[Dict]:
        """Get commits that modified files matching the patterns."""

        if not file_patterns:
            return []

        commits = []
        for pattern in file_patterns[:5]:  # Limit to first 5 patterns
            cmd = [
                "git", "-C", str(repo_path), "log",
                "--pretty=format:{\"sha\":\"%h\",\"message\":\"%s\",\"date\":\"%ad\",\"author\":\"%an\"}",
                "--date=iso",
                "--max-count=20",
                "--since=30 days ago",
                "--", pattern
            ]

            pattern_commits = await self._run_git_command(cmd, repo_path)
            commits.extend(pattern_commits)

        return commits

    async def _get_commits_by_keywords(self, repo_path: Path, keywords: List[str]) -> List[Dict]:
        """Get commits with messages containing keywords."""

        if not keywords:
            return []

        commits = []
        for keyword in keywords[:5]:  # Limit to first 5 keywords
            cmd = [
                "git", "-C", str(repo_path), "log",
                "--pretty=format:{\"sha\":\"%h\",\"message\":\"%s\",\"date\":\"%ad\",\"author\":\"%an\"}",
                "--date=iso",
                "--max-count=10",
                "--since=30 days ago",
                f"--grep={keyword}",
                "--regexp-ignore-case"
            ]

            keyword_commits = await self._run_git_command(cmd, repo_path)
            commits.extend(keyword_commits)

        return commits

    async def _run_git_command(self, cmd: List[str], repo_path: Path) -> List[Dict]:
        """Run a git command and parse the JSON output."""

        try:
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=10
            )

            stdout, stderr = await result.communicate()

            if result.returncode != 0:
                debug(f"Git command failed in {repo_path}: {stderr.decode()}")
                return []

            commits = []
            for line in stdout.decode().strip().split('\n'):
                if line:
                    try:
                        commit = json.loads(line)
                        commit['repo'] = repo_path.name
                        commits.append(commit)
                    except json.JSONDecodeError:
                        continue

            return commits

        except asyncio.TimeoutError:
            debug(f"Git command timed out in {repo_path}")
            return []
        except Exception as e:
            debug(f"Git command error in {repo_path}: {e}")
            return []

    def _calculate_commit_relevance(self, commit: Dict, search_params: Dict,
                                   insights: SessionInsights) -> tuple[float, List[str]]:
        """Calculate relevance score for a commit."""

        score = 0.0
        match_reasons = []

        message = commit.get("message", "").lower()

        # Keyword matching in commit message
        keywords = search_params.get("keywords", [])
        keyword_matches = sum(1 for keyword in keywords if keyword.lower() in message)
        if keyword_matches > 0:
            score += min(keyword_matches / len(keywords) * 0.5, 0.5) if keywords else 0
            match_reasons.append("keyword_match")

        # File pattern matching (if commit touches relevant files)
        file_patterns = search_params.get("file_patterns", [])
        if any(pattern.lower() in message for pattern in file_patterns):
            score += 0.3
            match_reasons.append("file_pattern")

        # Temporal relevance (recent commits)
        try:
            commit_date = datetime.fromisoformat(commit.get("date", ""))
            days_ago = (datetime.now(timezone.utc) - commit_date.replace(tzinfo=timezone.utc)).days
            if days_ago <= 7:
                score += 0.2 * (7 - days_ago) / 7
                match_reasons.append("recent_commit")
        except (ValueError, TypeError):
            pass

        # Common development actions
        dev_actions = ["fix", "add", "update", "implement", "refactor", "improve"]
        if any(action in message for action in dev_actions):
            score += 0.2
            match_reasons.append("development_action")

        return min(score, 1.0), list(set(match_reasons))

    def _format_commit_content(self, commit: Dict, repo_path: Path) -> str:
        """Format commit information for context inclusion."""

        formatted = f"## Commit in {repo_path.name}\n"
        formatted += f"**SHA:** {commit.get('sha', 'unknown')}\n"
        formatted += f"**Author:** {commit.get('author', 'unknown')}\n"
        formatted += f"**Date:** {commit.get('date', 'unknown')}\n"
        formatted += f"**Message:** {commit.get('message', 'No message')}\n\n"

        return formatted