import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

from recall.models import ParsedNote
from .base import BaseProvider

class ObsidianProvider(BaseProvider):
    """Extract notes from an Obsidian notebook at ~/Notebook."""

    def __init__(self, notebook_path: str = "~/Notebook"):
        self.notebook_path = Path(notebook_path).expanduser()

    def discover(self, date_range: Optional[Dict[str, datetime]] = None, **kwargs) -> List[str]:
        """Discover markdown files modified in the given date range."""
        if not self.notebook_path.exists():
            return []

        if date_range:
            cutoff = date_range['start']
        else:
            # Fallback if no date_range
            days = kwargs.get('days', 7)
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            
        notes = []

        for md_file in self.notebook_path.rglob("*.md"):
            # Skip hidden directories like .obsidian
            if any(part.startswith(".") for part in md_file.parts):
                continue

            mtime = datetime.fromtimestamp(md_file.stat().st_mtime, tz=timezone.utc)
            if mtime >= cutoff:
                notes.append(str(md_file))

        return notes

    def parse(self, filepath: str) -> Optional[ParsedNote]:
        """Parse an Obsidian markdown file into a ParsedNote."""
        try:
            path = Path(filepath)
            content = path.read_text()

            # Simple YAML frontmatter parsing
            tags = []
            title = path.stem

            frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
            if frontmatter_match:
                frontmatter_text = frontmatter_match.group(1)
                for line in frontmatter_text.split('\n'):
                    if line.startswith('tags:'):
                        # Simple tag extraction
                        tag_str = line.replace('tags:', '').strip()
                        tags = [t.strip().strip('[]"\'') for t in re.split(r'[,\s]+', tag_str) if t.strip()]
                    elif line.startswith('title:'):
                        title = line.replace('title:', '').strip().strip('"\'')

            # Extract tags from content (#tag)
            content_tags = re.findall(r'#([\w/-]+)', content)
            tags.extend(content_tags)

            # Times
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            ctime = datetime.fromtimestamp(path.stat().st_ctime, tz=timezone.utc)

            return ParsedNote(
                id=str(path.relative_to(self.notebook_path)),
                title=title,
                path=str(path),
                content=content,
                created_at=ctime,
                updated_at=mtime,
                tags=list(set(tags)),
                source="obsidian"
            )
        except Exception as e:
            print(f"  [obsidian] Parse error {filepath}: {e}")
            return None
    
    def extract(self, date_range: Dict[str, datetime], **kwargs) -> List[ParsedNote]:
        """Override extract to return List[ParsedNote]."""
        files = self.discover(date_range, **kwargs)
        notes = []
        for f in files:
            note = self.parse(f)
            if note:
                notes.append(note)
        return notes
