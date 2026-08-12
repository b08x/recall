from typing import Dict, List, Any
from recall.models import SessionInsights, ContextMatch
from recall.providers.context.base import ContextSource
from recall.logging import debug

class QMDContextSource(ContextSource):
    """Context source that uses QMD to query local markdown knowledge bases."""

    def __init__(self, notes_path: str = None):
        self.notes_path = notes_path

    async def find_relevant_content(self, insights: SessionInsights,
                                   session_context: Dict[str, Any]) -> List[ContextMatch]:
        """Query QMD for relevant notes based on insights."""
        debug("Querying QMD for relevant context")
        # Implementation would call qmd cli or library
        # For now, return empty or mock
        return []

    @property
    def source_type(self) -> str:
        return "qmd"

    async def is_available(self) -> bool:
        # Check if qmd is installed and notes_path exists
        return True
