try:
    import dspy
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False

from typing import List, Dict, Optional, Any
from .signatures import (
    SessionTopicExtractor, 
    CommitSessionCorrelator, 
    TimelineSynthesizer, 
    OneThingGenerator
)
from .chunking import ContextualChunker
from recall.logging import debug, info, error

if DSPY_AVAILABLE:
    class SessionAnalysisModule(dspy.Module):
        """Analyze sessions using contextual chunking to extract topics and actions."""

        def __init__(self, max_chunk_chars: int = 8000):
            super().__init__()
            self.extract_topics = dspy.ChainOfThought(SessionTopicExtractor)
            self.chunker = ContextualChunker(max_chunk_chars=max_chunk_chars)

        def forward(self, session: Any) -> Dict[str, Any]:
            """Process a session through contextual chunking and topic extraction."""
            debug(f"Chunking session {getattr(session, 'id', 'unknown')}")
            chunks = self.chunker.chunk_session(session)
            debug(f"Session split into {len(chunks)} chunks")
            
            all_topics = set()
            all_files = set()
            all_actions = set()

            for i, chunk in enumerate(chunks):
                debug(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk)} chars)")
                try:
                    result = self.extract_topics(session_content=chunk)
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


    class CorrelationModule(dspy.Module):
        """Multi-stage correlation pipeline."""

        def __init__(self):
            super().__init__()
            self.correlate_commits = dspy.Predict(CommitSessionCorrelator)
            self.synthesize = dspy.ChainOfThought(TimelineSynthesizer)
            self.one_thing = dspy.ChainOfThought(OneThingGenerator)

        def forward(self, sessions: List[Dict], commits: List[Dict], file_changes: List[Dict]):
            # Stage 1: Synthesize timeline
            timeline_result = self.synthesize(
                sessions=sessions,
                commits=commits,
                file_changes=file_changes
            )

            # Stage 2: Generate One Thing
            one_thing_result = self.one_thing(
                recent_activity=timeline_result.narrative,
                workstreams=timeline_result.workstreams,
                open_questions=[]  # Could be extracted from session analysis
            )

            return {
                "narrative": timeline_result.narrative,
                "workstreams": timeline_result.workstreams,
                "next_actions": timeline_result.next_actions,
                "one_thing": one_thing_result.one_thing,
                "one_thing_reasoning": one_thing_result.reasoning
            }

else:
    class SessionAnalysisModule: pass
    class CorrelationModule: pass
