from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from datetime import datetime
from recall.models import ParsedSession

class BaseProvider(ABC):
    """Abstract base class for all session providers."""

    @abstractmethod
    def discover(self, date_range: Optional[Dict[str, datetime]] = None, **kwargs) -> List[str]:
        """Discover session files/IDs."""
        pass

    @abstractmethod
    def parse(self, source_id: str) -> Optional[ParsedSession]:
        """Parse a single session source."""
        pass

    def extract(self, date_range: Dict[str, datetime], **kwargs) -> List[ParsedSession]:
        """Extract and parse sessions within the given date range."""
        sources = self.discover(date_range, **kwargs)
        sessions = []
        for source in sources:
            session = self.parse(source)
            if session:
                # Secondary filter in case discovery was over-broad
                if session.started_at and date_range['start'] <= session.started_at <= date_range['end']:
                    sessions.append(session)
                elif not session.started_at:
                    # If no timestamp, we might keep it or discard it. 
                    # For now, let's keep it if we can't prove it's outside range.
                    sessions.append(session)
        return sessions
