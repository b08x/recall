try:
    import dspy
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False

from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from .signatures import (
    SessionTopicExtractor, 
    SessionInsightExtractor,
    CommitSessionCorrelator, 
    TimelineSynthesizer, 
    OneThingGenerator
)
from .chunking import ContextualChunker
from recall.logging import debug, info, error
from recall.utils.limiter import get_default_limiter

if DSPY_AVAILABLE:
    class SessionAnalysisModule(dspy.Module):
        """Analyze sessions using contextual chunking to extract topics and actions."""

        def __init__(self, max_chunk_chars: int = 8000):
            super().__init__()
            self.extract_topics = dspy.ChainOfThought(SessionTopicExtractor)
            self.chunker = ContextualChunker(max_chunk_chars=max_chunk_chars)
            self.limiter = get_default_limiter()

        def forward(self, session: Any) -> Dict[str, Any]:
            """Process a session through contextual chunking and topic extraction."""
            debug(f"Chunking session {getattr(session, 'id', 'unknown')}")
            
            # Construct metadata for context
            platform = getattr(session, 'source_tool', 'unknown')
            project = getattr(session, 'project_name', 'unknown')
            started = getattr(session, 'started_at', datetime.now(timezone.utc)).isoformat()
            metadata = f"Platform: {platform} | Project: {project} | Date: {started}"
            
            chunks = self.chunker.chunk_session(session)
            debug(f"Session split into {len(chunks)} chunks")
            
            all_topics = set()
            all_files = set()
            all_actions = set()

            for i, chunk in enumerate(chunks):
                debug(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
                try:
                    self.limiter.wait()
                    result = self.extract_topics(
                        session_content=chunk,
                        context_metadata=metadata
                    )
                    if result:
                        if hasattr(result, 'topics'):
                            debug(f"Chunk {i+1} topics: {result.topics}")
                            all_topics.update(result.topics)
                        if hasattr(result, 'files_touched'):
                            all_files.update(result.files_touched)
                        if hasattr(result, 'key_actions'):
                            all_actions.update(result.key_actions)
                except Exception as e:
                    error(f"Error processing chunk {i+1}: {e}")

            return {
                "topics": sorted(list(all_topics)),
                "files_touched": sorted(list(all_files)),
                "key_actions": sorted(list(all_actions))
            }

    class SessionInsightModule(dspy.Module):
        """Extract categorized insights from sessions using typed predictor."""

        def __init__(self, max_chunk_chars: int = 12000):
            super().__init__()
            self.extract_insights = dspy.Predict(SessionInsightExtractor)
            self.chunker = ContextualChunker(max_chunk_chars=max_chunk_chars)
            self.limiter = get_default_limiter()

        def forward(self, session: Any) -> Dict[str, Any]:
            """Generate insights from session content."""
            debug(f"Extracting insights for session {getattr(session, 'id', 'unknown')}")
            
            # Construct metadata for context
            platform = getattr(session, 'source_tool', 'unknown')
            project = getattr(session, 'project_name', 'unknown')
            started = getattr(session, 'started_at', datetime.now(timezone.utc)).isoformat()
            metadata = f"Platform: {platform} | Project: {project} | Date: {started}"
            
            chunks = self.chunker.chunk_session(session)
            all_insights = []
            themes = []
            confidences = []

            for i, chunk in enumerate(chunks):
                try:
                    self.limiter.wait()
                    result = self.extract_insights(
                        session_content=chunk, 
                        context_metadata=metadata
                    )
                    if result:
                        if hasattr(result, 'insights'):
                            # result.insights is now a List[Insight] model instances
                            # We want to return dicts to maintain backward compatibility with the rest of the app
                            all_insights.extend([i.model_dump() for i in result.insights])
                        if hasattr(result, 'primary_theme'):
                            themes.append(result.primary_theme)
                        if hasattr(result, 'confidence'):
                            confidences.append(result.confidence)
                except Exception as e:
                    error(f"Error extracting insights from chunk {i+1}: {e}")

            return {
                "insights": all_insights,
                "primary_theme": max(set(themes), key=themes.count) if themes else "General",
                "confidence": sum(confidences) / len(confidences) if confidences else 0.0
            }


    class CorrelationModule(dspy.Module):
        """Multi-stage correlation pipeline."""

        def __init__(self):
            super().__init__()
            self.correlate_commits = dspy.Predict(CommitSessionCorrelator)
            self.synthesize = dspy.Predict(TimelineSynthesizer)
            self.one_thing = dspy.ChainOfThought(OneThingGenerator)
            self.limiter = get_default_limiter()

        def forward(self, sessions: List[Dict], commits: List[Dict], file_changes: List[Dict]):
            debug(f"CorrelationModule: synthesizing timeline from {len(sessions)} sessions and {len(commits)} commits")
            # Stage 1: Synthesize timeline
            self.limiter.wait()
            
            # Use Predict which expects Pydantic models for TimelineSynthesizer
            timeline_result = self.synthesize(
                sessions=sessions,
                commits=commits,
                file_changes=file_changes
            )
            debug(f"CorrelationModule: timeline synthesized. Narrative length: {len(timeline_result.narrative)}")

            # Stage 2: Generate One Thing
            debug("CorrelationModule: generating 'One Thing'")
            self.limiter.wait()
            one_thing_result = self.one_thing(
                recent_activity=timeline_result.narrative,
                workstreams=timeline_result.workstreams,
                open_questions=[]  # Could be extracted from session analysis
            )
            debug(f"CorrelationModule: 'One Thing' generated: {one_thing_result.one_thing[:50]}...")

            return {
                "narrative": timeline_result.narrative,
                "workstreams": timeline_result.workstreams,
                "next_actions": timeline_result.next_actions,
                "one_thing": one_thing_result.one_thing,
                "one_thing_reasoning": one_thing_result.reasoning
            }

else:
    class SessionAnalysisModule: pass
    class SessionInsightModule: pass
    class CorrelationModule: pass
