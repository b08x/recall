import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import asdict

from recall.models import ParsedSession, ParsedNote
from recall.providers.gemini import GeminiProvider
from recall.providers.hermes import HermesProvider
from recall.providers.claude_code import ClaudeCodeProvider
from recall.providers.opencode import OpenCodeProvider
from recall.providers.obsidian import ObsidianProvider
from recall.providers.local_git import LocalGitProvider
from recall.ai.modules import SessionAnalysisModule, CorrelationModule
from recall.config import Settings
from recall.logging import debug, info, error

try:
    import dspy
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False

class MultiSourceCorrelator:
    """Orchestrates session extraction, correlation, and analysis."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        
        self.providers = {
            "gemini": GeminiProvider(),
            "hermes": HermesProvider(),
            "claude": ClaudeCodeProvider(),
            "opencode": OpenCodeProvider()
        }
        self.obsidian = ObsidianProvider(str(self.settings.resolved_notebook_path))
        self.local_git = LocalGitProvider(str(self.settings.resolved_workspace_path))
        
        # DSPy configuration from settings
        self.dspy_provider = self.settings.dspy_provider
        self.dspy_model = self.settings.dspy_model

    def extract_all(self, days: int = 7, 
                    platforms: Optional[List[str]] = None,
                    analyze: bool = False,
                    model: Optional[str] = None,
                    callback: Optional[callable] = None) -> Dict[str, List[Any]]:
        """
        Extract sessions and notes from all platforms.
        
        Args:
            days: Number of days to look back.
            platforms: List of platforms to extract from.
            analyze: Whether to analyze session topics.
            model: Optional model override for analysis.
            callback: Optional callback for progress updates (e.g., for TUI).
        """
        debug(f"Starting extraction for last {days} days")
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        date_range = {'start': cutoff, 'end': datetime.now(timezone.utc)}
        
        results = {}
        all_platforms = list(self.providers.keys()) + ["obsidian"]
        target_platforms = platforms or all_platforms
        
        for platform in target_platforms:
            debug(f"Processing platform: {platform}")
            if callback:
                callback(f"Extracting from {platform}...", progress=0.2)
                
            if platform == "obsidian":
                notes = self.obsidian.extract(date_range)
                results["obsidian"] = notes
                debug(f"Extracted {len(notes)} notes from obsidian")
                continue

            if platform not in self.providers:
                debug(f"Platform {platform} not found in providers")
                continue
            
            provider = self.providers[platform]
            sessions = provider.extract(date_range)
            debug(f"Extracted {len(sessions)} sessions from {platform}")
            
            if analyze and sessions:
                debug(f"Analyzing {len(sessions)} sessions for {platform}")
                if callback:
                    callback(f"Analyzing {platform} sessions...", progress=0.5)
                for i, session in enumerate(sessions):
                    debug(f"Analyzing session {i+1}/{len(sessions)} (ID: {session.id})")
                    analysis = self.analyze_session_topics(session, model=model)
                    session.summary = analysis.get("topics", [])
                    if analysis.get("topics"):
                        session.generated_title = analysis["topics"][0]
                    debug(f"Analysis complete for session {session.id}: {session.summary}")
            
            results[platform] = sessions
        
        debug("Extraction all complete")
        if callback:
            callback("Extraction complete.", progress=1.0)
            
        return results

    def fetch_local_git_data(self, days: int = 7) -> List[Dict]:
        """Fetch commits from repositories in the workspace."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        date_range = {'start': cutoff, 'end': datetime.now(timezone.utc)}
        return self.local_git.extract_all(date_range)

    def fetch_github_data(self, repo: str, days: int = 7) -> Dict:
        """Fetch GitHub commits via gh CLI."""
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        # Check gh CLI
        result = subprocess.run(["gh", "--version"], capture_output=True)
        if result.returncode != 0:
            return {"commits": [], "pull_requests": []}
        
        commits = []
        try:
            # Prepare env with GITHUB_TOKEN if available
            env = os.environ.copy()
            if self.settings.github_token:
                env["GITHUB_TOKEN"] = self.settings.github_token.get_secret_value()

            result = subprocess.run([
                "gh", "api", f"repos/{repo}/commits",
                "--method", "GET",
                "--field", f"since={since}Z",
                "--jq", ".[] | {sha: .sha[0:7], message: .commit.message, date: .commit.author.date, author: .commit.author.name}"
            ], capture_output=True, text=True, env=env)
            
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        try:
                            commits.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except Exception:
            pass
        
        return {"commits": commits, "pull_requests": []}

    def build_timeline(self, sessions: Dict[str, List[Any]],
                       github_data: Optional[Dict] = None,
                       local_commits: Optional[List[Dict]] = None) -> List[Dict]:
        """Build unified timeline from all sources."""
        timeline = []
        
        for platform, items in sessions.items():
            for item in items:
                if isinstance(item, ParsedNote):
                    timeline.append({
                        "type": "note",
                        "platform": "obsidian",
                        "timestamp": item.updated_at,
                        "data": asdict(item),
                        "summary": f"Note: {item.title}"
                    })
                elif isinstance(item, ParsedSession):
                    timeline.append({
                        "type": "session",
                        "platform": platform,
                        "timestamp": item.started_at,
                        "data": asdict(item),
                        "summary": item.generated_title or f"{platform} session"
                    })
        
        if github_data:
            for commit in github_data.get("commits", []):
                try:
                    ts = datetime.fromisoformat(commit["date"].replace("Z", "+00:00"))
                except (KeyError, ValueError):
                    ts = datetime.now(timezone.utc)
                
                timeline.append({
                    "type": "commit",
                    "platform": "github",
                    "timestamp": ts,
                    "data": commit,
                    "summary": f"GitHub Commit: {commit.get('message', '').split('\n')[0][:60]}"
                })
        
        if local_commits:
            for commit in local_commits:
                try:
                    ts = datetime.fromisoformat(commit["date"])
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                except (KeyError, ValueError):
                    ts = datetime.now(timezone.utc)
                
                timeline.append({
                    "type": "commit",
                    "platform": f"git:{commit.get('repo', 'local')}",
                    "timestamp": ts,
                    "data": commit,
                    "summary": f"Local Commit: {commit.get('message', '').split('\n')[0][:60]}"
                })
        
        return sorted(timeline, key=lambda x: x.get("timestamp") or datetime.min.replace(tzinfo=timezone.utc))

    def configure_dspy(self, model: Optional[str] = None):
        """Configure DSPy with specified language model."""
        if not DSPY_AVAILABLE:
            return False
        
        provider = self.dspy_provider
        model_id = model or self.dspy_model
        
        try:
            if provider == 'openrouter':
                api_key = self.settings.openrouter_api_key
                if not api_key:
                    return False
                lm = dspy.LM(f"openrouter/{model_id}", api_key=api_key.get_secret_value(), base_url="https://openrouter.ai/api/v1")
            elif provider == 'openai':
                api_key = self.settings.openai_api_key
                if not api_key:
                    return False
                lm = dspy.LM(model_id, api_key=api_key.get_secret_value())
            elif provider == 'ollama':
                _, model_name = model_id.split("/", 1) if "/" in model_id else ("", model_id)
                lm = dspy.LM(f"ollama_chat/{model_name}")
            else:
                env_key = f"{provider.upper()}_API_KEY"
                api_key = getattr(self.settings, env_key.lower(), None)
                if api_key and hasattr(api_key, 'get_secret_value'):
                    lm = dspy.LM(f"{provider}/{model_id}", api_key=api_key.get_secret_value())
                else:
                    # Fallback to os.environ if not in settings
                    api_key_val = os.environ.get(env_key)
                    lm = dspy.LM(f"{provider}/{model_id}", api_key=api_key_val)
            
            dspy.configure(lm=lm)
            return True
        except Exception:
            return False

    def analyze_session_topics(self, session: ParsedSession, model: Optional[str] = None) -> Dict[str, Any]:
        """Use DSPy with contextual chunking to analyze session topics."""
        debug(f"Configuring DSPy for session analysis (model: {model or 'default'})")
        if not DSPY_AVAILABLE or not self.configure_dspy(model):
            debug("DSPy not available or configuration failed")
            return {"topics": [], "files_touched": [], "key_actions": []}
        
        debug("Running SessionAnalysisModule")
        analyzer = SessionAnalysisModule()
        try:
            result = analyzer(session)
            debug(f"SessionAnalysisModule result: {result}")
            return result
        except Exception as e:
            error(f"Error in SessionAnalysisModule: {e}")
            return {"topics": [], "files_touched": [], "key_actions": []}

    def correlate_with_dspy(self, timeline: List[Dict], model: Optional[str] = None) -> Dict:
        """Use DSPy to generate correlated narrative and next actions."""
        if not DSPY_AVAILABLE or not self.configure_dspy(model):
            return self._heuristic_correlation(timeline)
        
        sessions = [
            {
                "platform": t["platform"],
                "type": t["type"],
                "summary": t.get("summary", "Untitled"),
                "timestamp": t.get("timestamp", "").isoformat() if hasattr(t.get("timestamp"), "isoformat") else str(t.get("timestamp", ""))
            }
            for t in timeline if t["type"] in ["session", "note"]
        ][:20]
        
        commits = [
            {
                "message": t["data"].get("message", "").split("\n")[0][:100],
                "sha": t["data"].get("sha", "")[:8]
            }
            for t in timeline if t["type"] == "commit"
        ][:15]
        
        correlator = CorrelationModule()
        
        try:
            return correlator(sessions=sessions, commits=commits, file_changes=[])
        except Exception:
            return self._heuristic_correlation(timeline)

    def _heuristic_correlation(self, timeline: List[Dict]) -> Dict:
        """Fallback heuristic-based correlation."""
        sessions = [t for t in timeline if t["type"] == "session"]
        platforms = set(s["platform"] for s in sessions)
        return {
            "narrative": f"Activity across {len(platforms)} platforms: {', '.join(platforms)}",
            "workstreams": ["Recent activities"],
            "next_actions": ["Review recent sessions"]
        }
