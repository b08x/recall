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
    OneThingGenerator,
    ContextEnhancementSignature
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

        def forward(self, sessions: List[Dict], commits: List[Dict], file_changes: List[Dict], context_summary: Optional[str] = None):
            debug(f"CorrelationModule: synthesizing timeline from {len(sessions)} sessions and {len(commits)} commits")
            # Stage 1: Synthesize timeline
            self.limiter.wait()
            
            # Use Predict which expects Pydantic models for TimelineSynthesizer
            timeline_result = self.synthesize(
                sessions=sessions,
                commits=commits,
                file_changes=file_changes,
                context_summary=context_summary
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
                "strategic_insights": getattr(timeline_result, 'strategic_insights', []),
                "one_thing": one_thing_result.one_thing,
                "one_thing_reasoning": one_thing_result.reasoning
            }


    class ContextEnhancementModule(dspy.Module):
        """Enhance session insights using contextual information from multiple sources."""

        def __init__(self):
            super().__init__()
            self.enhance = dspy.Predict(ContextEnhancementSignature)
            self.limiter = get_default_limiter()

        def forward(self, base_insights: Dict[str, Any], context_matches: List[Dict[str, Any]],
                   session_metadata: Dict[str, Any] = None) -> Dict[str, Any]:
            """Enhance insights using context matches."""

            debug(f"Enhancing insights with {len(context_matches)} context matches")

            if not context_matches:
                debug("No context matches provided, returning base insights")
                return self._format_base_insights(base_insights)

            try:
                self.limiter.wait()

                # Prepare inputs for DSPy module
                original_insights_json = self._prepare_insights_json(base_insights)
                context_input = self._prepare_context_input(context_matches)
                metadata_str = self._prepare_metadata_string(session_metadata or {})

                # Call the enhancement module
                result = self.enhance(
                    original_insights=original_insights_json,
                    context_matches=context_input,
                    session_metadata=metadata_str
                )

                if result:
                    enhanced_result = {
                        "enhanced_insights": [insight.model_dump() for insight in result.enhanced_insights],
                        "knowledge_gaps_filled": result.knowledge_gaps_filled,
                        "strategic_recommendations": result.strategic_recommendations,
                        "confidence_assessment": result.confidence_assessment,
                        "enhancement_metadata": {
                            "sources_used": list(set(match["source_type"] for match in context_matches)),
                            "total_context_matches": len(context_matches),
                            "enhancement_method": "dspy_structured"
                        }
                    }
                    debug(f"Enhanced {len(result.enhanced_insights)} insights with context")
                    return enhanced_result

            except Exception as e:
                error(f"Context enhancement failed: {e}")

            # Fallback to basic enhancement
            debug("Falling back to basic context enhancement")
            return self._basic_enhancement(base_insights, context_matches)

        def _prepare_insights_json(self, base_insights: Dict[str, Any]) -> str:
            """Convert base insights to JSON string for DSPy input."""
            import json
            try:
                # Extract the insights structure that matches SessionInsights
                insights_data = {
                    "session_id": base_insights.get("session_id", "unknown"),
                    "insights": base_insights.get("insights", []),
                    "primary_theme": base_insights.get("primary_theme", "General"),
                    "confidence": base_insights.get("confidence", 0.0)
                }
                return json.dumps(insights_data)
            except Exception as e:
                error(f"Failed to prepare insights JSON: {e}")
                return "{}"

        def _prepare_context_input(self, context_matches: List[Dict[str, Any]]) -> List[Any]:
            """Convert context matches to DSPy input format."""
            from .signatures import ContextMatchInput

            prepared_matches = []
            for match in context_matches:
                try:
                    context_input = ContextMatchInput(
                        source_type=match.get("source_type", "unknown"),
                        content=match.get("content", "")[:1000],  # Limit content length
                        relevance_score=match.get("relevance_score", 0.0),
                        match_reasons=match.get("match_reasons", [])
                    )
                    prepared_matches.append(context_input)
                except Exception as e:
                    debug(f"Failed to prepare context match: {e}")
                    continue

            return prepared_matches

        def _prepare_metadata_string(self, session_metadata: Dict[str, Any]) -> str:
            """Prepare session metadata as a string."""
            try:
                metadata_parts = []
                for key, value in session_metadata.items():
                    if value:
                        metadata_parts.append(f"{key}: {value}")
                return " | ".join(metadata_parts)
            except Exception:
                return "No metadata available"

        def _format_base_insights(self, base_insights: Dict[str, Any]) -> Dict[str, Any]:
            """Format base insights when no enhancement is possible."""
            return {
                "enhanced_insights": base_insights.get("insights", []),
                "knowledge_gaps_filled": [],
                "strategic_recommendations": [],
                "confidence_assessment": "No context enhancement performed",
                "enhancement_metadata": {
                    "sources_used": [],
                    "total_context_matches": 0,
                    "enhancement_method": "none"
                }
            }

        def _basic_enhancement(self, base_insights: Dict[str, Any],
                              context_matches: List[Dict[str, Any]]) -> Dict[str, Any]:
            """Perform basic enhancement when DSPy processing fails."""

            insights = base_insights.get("insights", [])
            enhanced_insights = []

            # Simple keyword-based enhancement
            for insight in insights:
                enhanced_insight = insight.copy()

                # Find relevant context for this insight
                relevant_context = []
                insight_keywords = insight.get("content", "").lower().split()[:5]

                for match in context_matches:
                    match_content = match.get("content", "").lower()
                    if any(keyword in match_content for keyword in insight_keywords):
                        relevant_context.append(match)

                if relevant_context:
                    # Enhance the insight content with context
                    context_summary = f" [Context: {relevant_context[0].get('source_type', 'unknown')} source provides related information]"
                    enhanced_insight["content"] = insight.get("content", "") + context_summary
                    enhanced_insight["enhancement_confidence"] = min([m.get("relevance_score", 0.0) for m in relevant_context])
                    enhanced_insight["context_sources_used"] = [m.get("source_type", "unknown") for m in relevant_context]
                else:
                    enhanced_insight["enhancement_confidence"] = 0.0
                    enhanced_insight["context_sources_used"] = []

                enhanced_insights.append(enhanced_insight)

            # Extract knowledge gaps filled
            knowledge_gaps = []
            for match in context_matches:
                if "documentation" in match.get("match_reasons", []):
                    topic = match.get("content", "")[:50]
                    knowledge_gaps.append(topic)

            return {
                "enhanced_insights": enhanced_insights,
                "knowledge_gaps_filled": knowledge_gaps[:5],  # Limit to 5
                "strategic_recommendations": ["Review related documentation", "Consider similar patterns from git history"],
                "confidence_assessment": "Basic keyword-based enhancement applied",
                "enhancement_metadata": {
                    "sources_used": list(set(match.get("source_type", "unknown") for match in context_matches)),
                    "total_context_matches": len(context_matches),
                    "enhancement_method": "basic_fallback"
                }
            }

else:
    class SessionAnalysisModule: pass
    class SessionInsightModule: pass
    class CorrelationModule: pass
    class ContextEnhancementModule: pass
