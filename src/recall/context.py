"""Context source plugin system for enhancing session insights."""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime

from recall.models import SessionInsights, ContextMatch, EnhancedSessionInsights, ContextualInsight
from recall.config import Settings
from recall.logging import debug, info, error


class ContextSource(ABC):
    """Abstract base class for context source plugins."""

    @abstractmethod
    async def find_relevant_content(self, insights: SessionInsights,
                                   session_context: Dict[str, Any]) -> List[ContextMatch]:
        """Find context relevant to the given session insights.

        Args:
            insights: Base session insights to enhance
            session_context: Additional context about the session (project, files, etc.)

        Returns:
            List of ContextMatch objects with relevance scores
        """
        pass

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Unique identifier for this context source type."""
        pass

    async def is_available(self) -> bool:
        """Check if this context source is available and properly configured."""
        return True


class ContextSourceManager:
    """Manages context source plugins and orchestrates context enhancement."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.sources: Dict[str, ContextSource] = {}
        self._initialized = False

    def register_source(self, source: ContextSource):
        """Register a context source plugin."""
        self.sources[source.source_type] = source
        debug(f"Registered context source: {source.source_type}")

    async def initialize(self):
        """Initialize and validate all registered context sources."""
        if self._initialized:
            return

        available_sources = []
        for source_type, source in self.sources.items():
            try:
                if await source.is_available():
                    available_sources.append(source_type)
                    debug(f"Context source {source_type} is available")
                else:
                    info(f"Context source {source_type} is not available")
            except Exception as e:
                error(f"Failed to check availability of context source {source_type}: {e}")

        info(f"Initialized context sources: {available_sources}")
        self._initialized = True

    async def enhance_insights(self, insights: SessionInsights,
                              session_context: Dict[str, Any]) -> Optional[EnhancedSessionInsights]:
        """Enhance session insights with context from available sources.

        Args:
            insights: Base session insights to enhance
            session_context: Additional session context (project path, files touched, etc.)

        Returns:
            Enhanced insights or None if enhancement fails
        """
        if not self.settings.enable_context_enhancement:
            debug("Context enhancement disabled in settings")
            return None

        await self.initialize()

        if not self.sources:
            debug("No context sources available")
            return None

        try:
            # Gather context matches from all enabled sources in parallel
            context_tasks = []
            enabled_sources = []

            for source_type in self.settings.context_sources:
                if source_type in self.sources:
                    source = self.sources[source_type]
                    task = asyncio.create_task(
                        self._safe_find_content(source, insights, session_context)
                    )
                    context_tasks.append((source_type, task))
                    enabled_sources.append(source_type)

            if not context_tasks:
                debug("No enabled context sources found")
                return None

            # Wait for all context sources with timeout
            timeout = getattr(self.settings, 'context_enhancement_timeout', 30.0)
            all_context_matches = []
            sources_used = []

            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*[task for _, task in context_tasks], return_exceptions=True),
                    timeout=timeout
                )

                for (source_type, _), result in zip(context_tasks, results):
                    if isinstance(result, Exception):
                        error(f"Context source {source_type} failed: {result}")
                    elif result:
                        all_context_matches.extend(result)
                        sources_used.append(source_type)
                        debug(f"Got {len(result)} context matches from {source_type}")

            except asyncio.TimeoutError:
                error(f"Context enhancement timed out after {timeout}s")
                return None

            if not all_context_matches:
                debug("No relevant context found")
                return None

            # Filter by relevance threshold
            threshold = self.settings.context_relevance_threshold
            relevant_matches = [
                match for match in all_context_matches
                if match.relevance_score >= threshold
            ]

            if not relevant_matches:
                debug(f"No context matches above threshold {threshold}")
                return None

            # Sort by relevance and limit results
            relevant_matches.sort(key=lambda x: x.relevance_score, reverse=True)
            max_matches = self.settings.max_context_matches_per_source * len(sources_used)
            relevant_matches = relevant_matches[:max_matches]

            # Create enhanced insights
            enhanced_insights = await self._create_enhanced_insights(
                insights, relevant_matches, sources_used
            )

            info(f"Enhanced insights with {len(relevant_matches)} context matches from {sources_used}")
            return enhanced_insights

        except Exception as e:
            error(f"Context enhancement failed: {e}")
            return None

    async def _safe_find_content(self, source: ContextSource, insights: SessionInsights,
                                session_context: Dict[str, Any]) -> List[ContextMatch]:
        """Safely execute context source with error handling."""
        try:
            return await source.find_relevant_content(insights, session_context)
        except Exception as e:
            error(f"Context source {source.source_type} failed: {e}")
            return []

    async def _create_enhanced_insights(self, base_insights: SessionInsights,
                                      context_matches: List[ContextMatch],
                                      sources_used: List[str]) -> EnhancedSessionInsights:
        """Create enhanced insights from base insights and context matches."""

        # For now, create basic contextual insights
        # TODO: Use DSPy module for intelligent enhancement
        contextual_insights = []

        for insight in base_insights.insights:
            # Find context matches relevant to this specific insight
            relevant_context = [
                match for match in context_matches
                if any(keyword.lower() in match.content.lower()
                      for keyword in insight.content.split()[:5])  # Simple keyword matching
            ]

            if relevant_context:
                contextual_insight = ContextualInsight(
                    category=insight.category,
                    content=insight.content,
                    importance=insight.importance,
                    supporting_context=relevant_context[:3],  # Limit to top 3
                    context_sources_used=list(set(m.source_type for m in relevant_context)),
                    enhancement_confidence=min([m.relevance_score for m in relevant_context])
                )
                contextual_insights.append(contextual_insight)
            else:
                # Convert to contextual insight without context
                contextual_insight = ContextualInsight(
                    category=insight.category,
                    content=insight.content,
                    importance=insight.importance
                )
                contextual_insights.append(contextual_insight)

        # Identify knowledge gaps that were filled
        knowledge_gaps_filled = []
        for match in context_matches:
            if "documentation" in match.match_reasons or "knowledge" in match.content.lower():
                # Extract topic from context - simple heuristic
                topic = match.content.split('.')[0][:50]
                knowledge_gaps_filled.append(topic)

        # Additional suggested references (top context matches not used directly)
        suggested_references = [
            match for match in context_matches
            if not any(match in ci.supporting_context for ci in contextual_insights)
        ][:5]  # Limit to 5 suggestions

        return EnhancedSessionInsights(
            session_id=base_insights.session_id,
            base_insights=base_insights,
            contextual_insights=contextual_insights,
            knowledge_gaps_filled=list(set(knowledge_gaps_filled)),
            suggested_references=suggested_references,
            enhancement_metadata={
                "sources_used": sources_used,
                "total_context_matches": len(context_matches),
                "enhancement_method": "basic_keyword_matching"
            }
        )


def create_context_manager(settings: Settings) -> ContextSourceManager:
    """Factory function to create a configured ContextSourceManager."""
    manager = ContextSourceManager(settings)

    # Register available context sources based on settings
    if "obsidian" in settings.context_sources:
        try:
            from recall.providers.context.obsidian import ObsidianContextSource
            manager.register_source(ObsidianContextSource(settings))
        except ImportError:
            debug("ObsidianContextSource not available")

    if "git" in settings.context_sources:
        try:
            from recall.providers.context.git import GitContextSource
            manager.register_source(GitContextSource(settings))
        except ImportError:
            debug("GitContextSource not available")

    return manager