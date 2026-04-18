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
from recall.ai.modules import SessionAnalysisModule, SessionInsightModule, CorrelationModule
from recall.db import PersistenceManager
from recall.models import ParsedSession, ParsedNote, SessionAnalysis, SessionInsight, SessionInsights, CorrelationResult
from recall.config import Settings
from recall.logging import debug, info, error, step, log_metric, log_data
from recall.utils.limiter import RateLimiter, get_retry_decorator, rate_limited, set_default_limiter

try:
    import dspy
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False

class MultiSourceCorrelator:
    """Orchestrates session extraction, correlation, and analysis."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        
        # Rate Limiting - Initialize early so providers/db can use the global limiter
        self.limiter = RateLimiter(requests_per_minute=self.settings.requests_per_minute)
        set_default_limiter(self.limiter)

        self.providers = {
            "gemini": GeminiProvider(),
            "hermes": HermesProvider(),
            "claude": ClaudeCodeProvider(),
            "opencode": OpenCodeProvider()
        }
        self.obsidian = ObsidianProvider(str(self.settings.resolved_notebook_path))
        self.local_git = LocalGitProvider(str(self.settings.resolved_workspace_path))
        
        # Persistence Layer
        self.db = PersistenceManager(
            db_path=self.settings.db_path,
            vector_dir=self.settings.vector_db_dir,
            ollama_host=self.settings.ollama_host
        )
        
        # DSPy configuration from settings
        self.dspy_provider = self.settings.dspy_provider
        self.dspy_model = self.settings.dspy_model
        
    def estimate_session_tokens(self, sessions: List[ParsedSession]) -> int:
        """Estimate the total number of tokens across a list of sessions."""
        try:
            import tiktoken
            encoding = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            # Fallback to rough character-based estimation (4 chars per token)
            return sum(len(m.content or "") for s in sessions for m in s.messages) // 4

        total = 0
        for s in sessions:
            for m in s.messages:
                total += len(encoding.encode(m.content or ""))
        return total

    def extract_all(self, days: int = 7, 
                    platforms: Optional[List[str]] = None,
                    analyze: bool = False,
                    overwrite: bool = False,
                    model: Optional[str] = None,
                    insights_model: Optional[str] = None,
                    insights_provider: Optional[str] = None,
                    callback: Optional[callable] = None) -> Dict[str, List[Any]]:
        """
        Extract sessions and notes from all platforms and persist them.
        """
        debug(f"Starting extraction for last {days} days")
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        date_range = {'start': cutoff, 'end': datetime.now(timezone.utc)}
        
        # Determine models to use
        analysis_model = model or self.dspy_model
        insights_model = insights_model or self.settings.dspy_insights_model or analysis_model
        insights_provider = insights_provider or self.settings.dspy_insights_provider or self.dspy_provider
        
        results = {}
        all_platforms = list(self.providers.keys()) + ["obsidian"]
        target_platforms = platforms or all_platforms
        
        log_metric("extract_all_started", 1)
        log_metric("target_platforms", len(target_platforms))
        
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
            
            for i, session in enumerate(sessions):
                analysis_obj = None
                insight_obj = None
                if analyze:
                    # Check for existing analysis/insights unless overwrite is True
                    existing_analysis = None
                    existing_insights = None
                    if not overwrite:
                        existing_analysis = self.db.get_analysis(session.id)
                        existing_insights = self.db.get_insights(session.id)
                    else:
                        debug(f"Overwrite enabled: forcing re-analysis for session {session.id}")
                    
                    if existing_analysis:
                        debug(f"Found existing analysis for {session.id}")
                        session.summary = existing_analysis.topics
                        if session.summary:
                            session.generated_title = session.summary[0]
                        analysis_obj = existing_analysis
                        insight_obj = existing_insights
                    else:
                        debug(f"Analyzing session {i+1}/{len(sessions)} (ID: {session.id})")
                        if callback:
                            callback(f"Analyzing {platform} {i+1}/{len(sessions)}...", progress=0.5)
                        
                        # 1. Topic/Activity Analysis
                        analysis_data = self.analyze_session_topics(session, model=analysis_model)
                        session.summary = analysis_data.get("topics", [])
                        if session.summary:
                            session.generated_title = session.summary[0]
                        
                        analysis_obj = SessionAnalysis(
                            session_id=session.id,
                            topics=analysis_data.get("topics", []),
                            files_touched=analysis_data.get("files_touched", []),
                            key_actions=analysis_data.get("key_actions", []),
                            analyzed_at=datetime.now(timezone.utc)
                        )

                        # 2. Insight Extraction
                        insight_data = self.analyze_session_insights(session, model=insights_model, provider=insights_provider)
                        
                        valid_insights = []
                        for i in insight_data.get("insights", []):
                            if isinstance(i, dict):
                                # Filter only valid keys for SessionInsight and ensure types are correct
                                try:
                                    # Extract core fields, providing defaults if missing
                                    category = str(i.get("category", "General")).upper()
                                    content = str(i.get("content", ""))
                                    
                                    # Handle case where LLM might have put content in a weird key or it's missing
                                    if not content:
                                        potential_content = []
                                        for k, v in i.items():
                                            if k in ["category", "importance"]:
                                                continue
                                            
                                            # Collect long strings from both keys and values
                                            if isinstance(k, str) and len(k) > 50:
                                                potential_content.append(k)
                                            if isinstance(v, str) and len(v) > 50:
                                                potential_content.append(v)
                                        
                                        if potential_content:
                                            # Join them together as they might be parts of the same insight
                                            content = " ".join(potential_content).strip()
                                    
                                    if not content:
                                        # One last try: if there's only one extra key and it has a value, use it
                                        extra_keys = [k for k in i.keys() if k not in ["category", "importance", "content"]]
                                        if len(extra_keys) == 1:
                                            k = extra_keys[0]
                                            v = i[k]
                                            content = f"{k}: {v}" if isinstance(v, (str, int, float)) else k
                                    
                                    if not content:
                                        continue
                                        
                                    importance = i.get("importance", 0.5)
                                    try:
                                        importance = float(importance)
                                    except (ValueError, TypeError):
                                        importance = 0.5
                                        
                                    valid_insights.append(SessionInsight(
                                        category=category,
                                        content=content,
                                        importance=importance
                                    ))
                                except Exception as e:
                                    debug(f"Skipping malformed insight: {e}")
                                    continue

                        insight_obj = SessionInsights(
                            session_id=session.id,
                            insights=valid_insights,
                            primary_theme=insight_data.get("primary_theme", "General"),
                            confidence=insight_data.get("confidence", 0.0),
                            generated_at=datetime.now(timezone.utc)
                        )
                else:
                    debug(f"Skipping analysis for session {session.id} (analyze=False)")
                
                # Persist each session as it is processed
                debug(f"Persisting session {session.id} to storage")
                self.db.persist_session(session, analysis_obj, insight_obj, overwrite=overwrite)
            
            results[platform] = sessions
            log_metric("sessions_per_platform", len(sessions))
        
        debug("Extraction all complete")
        if callback:
            callback("Extraction complete.", progress=1.0)
            
        return results
        
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
        @get_retry_decorator(
            max_attempts=self.settings.retry_max_attempts,
            min_wait=self.settings.retry_min_wait,
            max_wait=self.settings.retry_max_wait
        )
        def _fetch():
            self.limiter.wait()
            since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            
            # Check gh CLI
            result = subprocess.run(["gh", "--version"], capture_output=True)
            if result.returncode != 0:
                return {"commits": [], "pull_requests": []}
            
            commits = []
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
            
            if result.returncode != 0:
                error(f"GitHub API error: {result.stderr}")
                raise Exception(f"GitHub API returned exit code {result.returncode}")

            for line in result.stdout.strip().split("\n"):
                if line:
                    try:
                        commits.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            return {"commits": commits, "pull_requests": []}

        try:
            return _fetch()
        except Exception as e:
            error(f"Failed to fetch GitHub data after retries: {e}")
            return {"commits": [], "pull_requests": []}

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

    def configure_dspy(self, model: Optional[str] = None, provider: Optional[str] = None):
        """Configure DSPy with specified language model."""
        if not DSPY_AVAILABLE:
            return False
        
        provider = provider or self.dspy_provider
        model_id = model or self.dspy_model
        
        try:
            if provider == 'openrouter':
                api_key = self.settings.openrouter_api_key
                if not api_key:
                    return False
                lm = dspy.LM(f"openrouter/{model_id}", api_key=api_key.get_secret_value(), base_url="https://openrouter.ai/api/v1", num_retries=self.settings.retry_max_attempts)
            elif provider == 'openai':
                api_key = self.settings.openai_api_key
                if not api_key:
                    return False
                lm = dspy.LM(model_id, api_key=api_key.get_secret_value(), num_retries=self.settings.retry_max_attempts)
            elif provider == 'mistral':
                api_key = self.settings.mistral_api_key
                if not api_key:
                    return False
                lm = dspy.LM(f"mistral/{model_id}", api_key=api_key.get_secret_value(), num_retries=self.settings.retry_max_attempts)
            elif provider == 'ollama':
                _, model_name = model_id.split("/", 1) if "/" in model_id else ("", model_id)
                lm = dspy.LM(f"ollama_chat/{model_name}", num_retries=self.settings.retry_max_attempts)
            else:
                env_key = f"{provider.upper()}_API_KEY"
                api_key = getattr(self.settings, env_key.lower(), None)
                if api_key and hasattr(api_key, 'get_secret_value'):
                    lm = dspy.LM(f"{provider}/{model_id}", api_key=api_key.get_secret_value(), num_retries=self.settings.retry_max_attempts)
                else:
                    # Fallback to os.environ if not in settings
                    api_key_val = os.environ.get(env_key)
                    lm = dspy.LM(f"{provider}/{model_id}", api_key=api_key_val, num_retries=self.settings.retry_max_attempts)
            
            dspy.configure(lm=lm, adapter=dspy.ChatAdapter())
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
            self.limiter.wait()
            result = analyzer(session)
            debug(f"SessionAnalysisModule result: {result}")
            return result
        except Exception as e:
            error(f"Error in SessionAnalysisModule: {e}")
            return {"topics": [], "files_touched": [], "key_actions": []}

    def analyze_session_insights(self, session: ParsedSession, model: Optional[str] = None, provider: Optional[str] = None) -> Dict[str, Any]:
        """Use DSPy to extract categorized insights from a session."""
        debug(f"Configuring DSPy for session insights (model: {model or 'default'})")
        if not DSPY_AVAILABLE or not self.configure_dspy(model, provider):
            return {"insights": [], "primary_theme": "General", "confidence": 0.0}
        
        debug("Running SessionInsightModule")
        analyzer = SessionInsightModule()
        try:
            self.limiter.wait()
            result = analyzer(session)
            debug(f"SessionInsightModule result: {result}")
            return result
        except Exception as e:
            error(f"Error in SessionInsightModule: {e}")
            return {"insights": [], "primary_theme": "General", "confidence": 0.0}

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
            self.limiter.wait()
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
