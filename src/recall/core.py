import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
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
from recall.utils.limiter import get_limiter, get_retry_decorator, rate_limited, set_global_rpm

try:
    import dspy
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
    _TIKTOKEN_ENCODING = tiktoken.get_encoding("cl100k_base")
except ImportError:
    TIKTOKEN_AVAILABLE = False
    _TIKTOKEN_ENCODING = None

class MultiSourceCorrelator:
    """Orchestrates session extraction, correlation, and analysis."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings()
        
        # Rate Limiting - Configure global RPM and use named limiters
        set_global_rpm(self.settings.requests_per_minute)

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
            ollama_host=self.settings.ollama_host,
            ollama_model=self.settings.embedding_model,
            embedding_max_tokens=self.settings.embedding_max_tokens,
            chunk_max_chars=self.settings.chunk_max_chars
        )
        
        # DSPy configuration from settings
        self.dspy_provider = self.settings.dspy_provider
        self.dspy_model = self.settings.dspy_model

        # Run reconciliation for any failed indexing jobs from previous runs
        self.db.reconcile_failed_vectors()

    def estimate_session_tokens(self, sessions: List[ParsedSession]) -> int:
        """Estimate the total number of tokens across a list of sessions."""
        if not TIKTOKEN_AVAILABLE or not _TIKTOKEN_ENCODING:
            import re
            # Better fallback: count words and non-whitespace symbols
            # This is more accurate for code and structured data than simple char // 4
            total = 0
            for s in sessions:
                for m in s.messages:
                    content = m.content or ""
                    # This regex matches words or non-whitespace characters
                    tokens = re.findall(r"\w+|[^\w\s]", content)
                    # Heuristic: tokens + 10% for some overhead/whitespace that might be meaningful
                    total += int(len(tokens) * 1.1)
            return total

        total = 0
        for s in sessions:
            for m in s.messages:
                total += len(_TIKTOKEN_ENCODING.encode(m.content or ""))
        return total

    def _process_single_session(self, 
                               session: ParsedSession, 
                               platform: str,
                               analyze: bool, 
                               overwrite: bool, 
                               analysis_model: str, 
                               insights_model: str, 
                               insights_provider: str,
                               callback: Optional[callable] = None):
        """Analyze and persist a single session. Designed to be run in a thread pool."""
        analysis_obj = None
        insight_obj = None
        
        if analyze:
            # Check for existing analysis/insights unless overwrite is True
            existing_analysis = None
            existing_insights = None
            if not overwrite:
                existing_analysis = self.db.get_analysis(session.id)
                existing_insights = self.db.get_insights(session.id)
            
            if existing_analysis:
                debug(f"Found existing analysis for {session.id}")
                session.summary = existing_analysis.topics
                if session.summary:
                    session.generated_title = session.summary[0]
                analysis_obj = existing_analysis
                insight_obj = existing_insights
            else:
                debug(f"Analyzing session (ID: {session.id})")
                
                # 1. Topic/Activity Analysis
                analysis_data = self.analyze_session_topics(session, model=analysis_model, provider=platform)
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

                # 2. Insight Extraction (REC-002: Simplified Parsing)
                # Pass the platform as the provider for rate limiting
                insight_data = self.analyze_session_insights(
                    session, 
                    model=insights_model, 
                    provider=insights_provider or platform
                )
                
                valid_insights = []
                for i in insight_data.get("insights", []):
                    # Trust the structured Pydantic payload from DSPy module
                    if isinstance(i, dict) and "content" in i:
                        valid_insights.append(SessionInsight(
                            category=i.get("category", "GENERAL").upper(),
                            content=i.get("content", ""),
                            importance=float(i.get("importance", 0.5))
                        ))

                insight_obj = SessionInsights(
                    session_id=session.id,
                    insights=valid_insights,
                    primary_theme=insight_data.get("primary_theme", "General"),
                    confidence=insight_data.get("confidence", 0.0),
                    generated_at=datetime.now(timezone.utc)
                )
        else:
            debug(f"Skipping analysis for session {session.id} (analyze=False)")
        
        # Persist session
        debug(f"Persisting session {session.id} to storage")
        try:
            self.db.persist_session(session, analysis_obj, insight_obj, overwrite=overwrite)
        except Exception as e:
            error(f"Failed to persist session {session.id}: {e}")

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
        Uses ThreadPoolExecutor for concurrent analysis and persistence.
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
        
        # Track futures with their session metadata for DLQ/Retry
        future_to_session = {}
        
        with ThreadPoolExecutor(max_workers=self.settings.max_workers) as executor:
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
                results[platform] = sessions
                log_metric("sessions_per_platform", len(sessions))
                
                for session in sessions:
                    payload = {
                        "session": session,
                        "platform": platform,
                        "analyze": analyze,
                        "overwrite": overwrite,
                        "analysis_model": analysis_model,
                        "insights_model": insights_model,
                        "insights_provider": insights_provider
                    }
                    future = executor.submit(
                        self._process_single_session,
                        session, platform, analyze, overwrite,
                        analysis_model, insights_model, insights_provider, callback
                    )
                    future_to_session[future] = payload
            
            # Wait for all sessions to be processed with retry logic
            for future in future_to_session:
                payload = future_to_session[future]
                session_id = payload["session"].id
                try:
                    future.result()
                except Exception as e:
                    error(f"Transient error processing session {session_id}, retrying once: {e}")
                    # Explicit one-time retry for transient errors
                    try:
                        self._process_single_session(
                            payload["session"], payload["platform"], payload["analyze"], 
                            payload["overwrite"], payload["analysis_model"], 
                            payload["insights_model"], payload["insights_provider"], callback
                        )
                        info(f"Successfully recovered session {session_id} on retry")
                    except Exception as retry_e:
                        error(f"Final failure for session {session_id}: {retry_e}")
                        self.db.save_dlq_item(
                            session_id=session_id,
                            payload=payload,
                            error_msg=str(retry_e)
                        )
        
        dlq_items = self.db.get_dlq_items()
        if dlq_items:
            error(f"Extraction completed with {len(dlq_items)} items in Dead Letter Queue")
            log_data("dlq_items", [item["session_id"] for item in dlq_items])
        
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
            get_limiter("github").wait()
            since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            
            # Check gh CLI
            result = subprocess.run(["gh", "--version"], capture_output=True, timeout=30)
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
            ], capture_output=True, text=True, env=env, timeout=30)
            
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
        debug("Building unified timeline from sessions, github, and local git")
        timeline = []
        
        for platform, items in sessions.items():
            debug(f"Adding {len(items)} items from {platform} to timeline")
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
            github_commits = github_data.get("commits", [])
            debug(f"Adding {len(github_commits)} GitHub commits to timeline")
            for commit in github_commits:
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
            debug(f"Adding {len(local_commits)} local git commits to timeline")
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
        
        sorted_timeline = sorted(timeline, key=lambda x: x.get("timestamp") or datetime.min.replace(tzinfo=timezone.utc))
        debug(f"Timeline built with {len(sorted_timeline)} total events")
        return sorted_timeline

    def retry_dlq(self, callback: Optional[callable] = None) -> List[Any]:
        """Retry all failed sessions in the Dead Letter Queue."""
        dlq_items = self.db.get_dlq_items()
        if not dlq_items:
            info("No items in DLQ to retry.")
            return []

        info(f"Retrying {len(dlq_items)} items from DLQ...")
        results = []
        
        # Process items. Since they failed before, we process them sequentially for better error tracking.
        for item in dlq_items:
            dlq_id = item["id"]
            payload = item["payload"]
            session_id = item["session_id"]
            
            # Reconstruct ParsedSession if it was serialized as dict
            # MultiSourceCorrelator expects ParsedSession object in payload["session"]
            # if we want to reuse _process_single_session
            
            from recall.models import ParsedSession, ParsedMessage, SessionUsage, ToolCall, ToolResult
            
            def dict_to_session(d):
                # Simple reconstruction
                if not d: return None
                msgs = []
                for m in d.get("messages", []):
                    msgs.append(ParsedMessage(
                        id=m.get("id"),
                        session_id=m.get("session_id"),
                        type=m.get("type"),
                        content=m.get("content"),
                        thinking=m.get("thinking"),
                        timestamp=datetime.fromisoformat(m["timestamp"]) if m.get("timestamp") else None,
                        parent_id=m.get("parent_id"),
                        usage=m.get("usage"),
                        tool_calls=[ToolCall(**tc) for tc in m.get("tool_calls", [])],
                        tool_results=[ToolResult(**tr) for tr in m.get("tool_results", [])]
                    ))
                
                usage_data = d.get("usage")
                usage = SessionUsage(**usage_data) if usage_data else None
                
                return ParsedSession(
                    id=d["id"],
                    project_path=d.get("project_path"),
                    project_name=d.get("project_name"),
                    started_at=datetime.fromisoformat(d["started_at"]) if d.get("started_at") else None,
                    ended_at=datetime.fromisoformat(d["ended_at"]) if d.get("ended_at") else None,
                    message_count=d.get("message_count", 0),
                    user_message_count=d.get("user_message_count", 0),
                    assistant_message_count=d.get("assistant_message_count", 0),
                    tool_call_count=d.get("tool_call_count", 0),
                    source_tool=d.get("source_tool", "unknown"),
                    usage=usage,
                    messages=msgs,
                    generated_title=d.get("generated_title"),
                    summary=d.get("summary"),
                    git_branch=d.get("git_branch"),
                    claude_version=d.get("claude_version")
                )

            session_obj = dict_to_session(payload.get("session"))
            if not session_obj:
                error(f"Could not reconstruct session {session_id} from DLQ payload")
                continue

            try:
                self._process_single_session(
                    session=session_obj,
                    platform=payload.get("platform", "unknown"),
                    analyze=payload.get("analyze", True),
                    overwrite=payload.get("overwrite", False),
                    analysis_model=payload.get("analysis_model"),
                    insights_model=payload.get("insights_model"),
                    insights_provider=payload.get("insights_provider"),
                    callback=callback
                )
                info(f"Successfully processed DLQ item {session_id}")
                self.db.delete_dlq_item(dlq_id)
                results.append(session_id)
            except Exception as e:
                error(f"Retry failed for DLQ item {session_id}: {e}")
                self.db.increment_dlq_retry(dlq_id)
        
        return results

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

    def analyze_session_topics(self, session: ParsedSession, model: Optional[str] = None, provider: str = "default") -> Dict[str, Any]:
        """Use DSPy with contextual chunking to analyze session topics."""
        debug(f"Configuring DSPy for session analysis (model: {model or 'default'})")
        if not DSPY_AVAILABLE or not self.configure_dspy(model):
            debug("DSPy not available or configuration failed")
            return {"topics": [], "files_touched": [], "key_actions": []}
        
        debug("Running SessionAnalysisModule")
        analyzer = SessionAnalysisModule()
        analyzer.limiter = get_limiter(provider)
        try:
            # We still wait once here to ensure the session processing itself is spaced out
            analyzer.limiter.wait()
            result = analyzer(session)
            debug(f"SessionAnalysisModule result: {result}")
            return result
        except Exception as e:
            error(f"Error in SessionAnalysisModule: {e}")
            return {"topics": [], "files_touched": [], "key_actions": []}

    def analyze_session_insights(self, session: ParsedSession, model: Optional[str] = None, provider: Optional[str] = None) -> Dict[str, Any]:
        """Use DSPy to extract categorized insights from a session."""
        debug(f"Configuring DSPy for session insights (model: {model or 'default'})")
        # Use insights_provider if specified, otherwise the dspy_provider
        active_provider = provider or self.settings.dspy_insights_provider or self.dspy_provider
        
        if not DSPY_AVAILABLE or not self.configure_dspy(model, provider):
            return {"insights": [], "primary_theme": "General", "confidence": 0.0}
        
        debug("Running SessionInsightModule")
        analyzer = SessionInsightModule()
        analyzer.limiter = get_limiter(active_provider)
        try:
            analyzer.limiter.wait()
            result = analyzer(session)
            debug(f"SessionInsightModule result: {result}")
            return result
        except Exception as e:
            error(f"Error in SessionInsightModule: {e}")
            return {"insights": [], "primary_theme": "General", "confidence": 0.0}

    def correlate_with_dspy(self, timeline: List[Dict], model: Optional[str] = None) -> Dict:
        """Use DSPy to generate correlated narrative and next actions."""
        debug(f"Correlating {len(timeline)} events with DSPy")
        if not DSPY_AVAILABLE or not self.configure_dspy(model):
            debug("DSPy not available, falling back to heuristic correlation")
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
        
        debug(f"Prepared {len(sessions)} sessions and {len(commits)} commits for correlation")
        correlator = CorrelationModule()
        correlator.limiter = get_limiter("correlation")
        
        try:
            correlator.limiter.wait()
            result = correlator(sessions=sessions, commits=commits, file_changes=[])
            debug("DSPy correlation successful")
            return result
        except Exception as e:
            error(f"Error during DSPy correlation: {e}")
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
