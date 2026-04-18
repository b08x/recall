import json
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

class LocalGitProvider:
    """Extract git activity from all repositories in ~/Workspace."""

    def __init__(self, workspace_path: str = "~/Workspace"):
        self.workspace_path = Path(workspace_path).expanduser()

    def discover(self) -> List[Path]:
        """Discover all git repositories in the workspace."""
        if not self.workspace_path.exists():
            return []

        repos = []
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
        return repos

    def extract_commits(self, repo_path: Path, date_range: Dict[str, datetime]) -> List[Dict]:
        """Extract commits from a specific repository."""
        since = date_range['start'].strftime('%Y-%m-%d %H:%M:%S')
        until = date_range['end'].strftime('%Y-%m-%d %H:%M:%S')

        cmd = [
            "git", "-C", str(repo_path), "log",
            f"--since={since}",
            f"--until={until}",
            "--pretty=format:{\"sha\":\"%h\",\"message\":\"%s\",\"date\":\"%ad\",\"author\":\"%an\"}",
            "--date=iso"
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            commits = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    try:
                        commit = json.loads(line)
                        commit['repo'] = repo_path.name
                        commits.append(commit)
                    except json.JSONDecodeError:
                        continue
            return commits
        except subprocess.CalledProcessError:
            return []

    def extract_all(self, date_range: Dict[str, datetime]) -> List[Dict]:
        """Extract commits from all discovered repositories."""
        repos = self.discover()
        all_commits = []
        for repo in repos:
            all_commits.extend(self.extract_commits(repo, date_range))
        return all_commits
