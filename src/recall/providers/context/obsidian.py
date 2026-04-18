"""Obsidian context source for enhancing session insights with relevant documentation."""

import re
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from recall.context import ContextSource
from recall.models import SessionInsights, ContextMatch, ParsedNote
from recall.config import Settings
from recall.logging import debug, error


class ObsidianContextSource(ContextSource):
    """Context source that finds relevant Obsidian notes to enhance session insights."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.notebook_path = settings.resolved_notebook_path
        self._note_cache: Dict[str, ParsedNote] = {}
        self._last_cache_update: Optional[datetime] = None

    @property
    def source_type(self) -> str:
        return "obsidian"

    async def is_available(self) -> bool:
        """Check if Obsidian notebook exists and is accessible."""
        return self.notebook_path.exists() and self.notebook_path.is_dir()

    async def find_relevant_content(self, insights: SessionInsights,
                                   session_context: Dict[str, Any]) -> List[ContextMatch]:
        """Find Obsidian notes relevant to the session insights using hybrid matching."""

        if not await self.is_available():
            debug("Obsidian notebook not available")
            return []

        try:
            # Update note cache if needed
            await self._update_note_cache()

            if not self._note_cache:
                debug("No notes found in Obsidian notebook")
                return []

            # Extract search terms from insights
            search_terms = self._extract_search_terms(insights, session_context)
            if not search_terms:
                debug("No search terms extracted from insights")
                return []

            # Find relevant notes using hybrid matching
            context_matches = []

            for note_id, note in self._note_cache.items():
                relevance_score, match_reasons = await self._calculate_relevance(
                    note, search_terms, insights, session_context
                )

                if relevance_score > 0:
                    context_matches.append(ContextMatch(
                        source_type=self.source_type,
                        content=self._format_note_content(note),
                        relevance_score=relevance_score,
                        match_reasons=match_reasons,
                        metadata={
                            "note_id": note_id,
                            "title": note.title,
                            "path": note.path,
                            "tags": note.tags,
                            "updated_at": note.updated_at.isoformat() if note.updated_at else None
                        }
                    ))

            # Sort by relevance score
            context_matches.sort(key=lambda x: x.relevance_score, reverse=True)

            debug(f"Found {len(context_matches)} relevant notes")
            return context_matches

        except Exception as e:
            error(f"Failed to find relevant Obsidian content: {e}")
            return []

    async def _update_note_cache(self):
        """Update the internal cache of notes if needed."""

        # Check if cache is recent enough (5 minutes)
        if (self._last_cache_update and
            datetime.now(timezone.utc) - self._last_cache_update < timedelta(minutes=5)):
            return

        debug("Updating Obsidian note cache")
        self._note_cache.clear()

        # Look for notes modified in the last 30 days (configurable window)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)

        for md_file in self.notebook_path.rglob("*.md"):
            # Skip hidden directories like .obsidian
            if any(part.startswith(".") for part in md_file.parts):
                continue

            try:
                mtime = datetime.fromtimestamp(md_file.stat().st_mtime, tz=timezone.utc)
                if mtime >= cutoff:
                    note = self._parse_note(md_file)
                    if note:
                        self._note_cache[note.id] = note
            except Exception as e:
                debug(f"Failed to parse note {md_file}: {e}")
                continue

        self._last_cache_update = datetime.now(timezone.utc)
        debug(f"Cached {len(self._note_cache)} recent notes")

    def _parse_note(self, filepath: Path) -> Optional[ParsedNote]:
        """Parse an Obsidian markdown file into a ParsedNote."""
        try:
            content = filepath.read_text(encoding='utf-8')

            # Simple YAML frontmatter parsing
            tags = []
            title = filepath.stem

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
            mtime = datetime.fromtimestamp(filepath.stat().st_mtime, tz=timezone.utc)
            ctime = datetime.fromtimestamp(filepath.stat().st_ctime, tz=timezone.utc)

            return ParsedNote(
                id=str(filepath.relative_to(self.notebook_path)),
                title=title,
                path=str(filepath),
                content=content,
                created_at=ctime,
                updated_at=mtime,
                tags=list(set(tags)),
                source="obsidian"
            )
        except Exception as e:
            debug(f"Parse error {filepath}: {e}")
            return None

    def _extract_search_terms(self, insights: SessionInsights,
                             session_context: Dict[str, Any]) -> Dict[str, List[str]]:
        """Extract search terms from insights and session context."""
        search_terms = {
            "topics": [],
            "files": [],
            "keywords": [],
            "theme": []
        }

        # Extract from insights
        for insight in insights.insights:
            # Extract keywords from insight content
            words = re.findall(r'\b[a-zA-Z]{3,}\b', insight.content.lower())
            search_terms["keywords"].extend(words[:10])  # Limit to first 10 words

        # Add primary theme
        if insights.primary_theme:
            search_terms["theme"] = [insights.primary_theme.lower()]

        # Extract from session context
        if "files_touched" in session_context:
            files = session_context["files_touched"]
            search_terms["files"] = [Path(f).stem for f in files if f]

        if "topics" in session_context:
            search_terms["topics"] = [t.lower() for t in session_context["topics"]]

        return search_terms

    async def _calculate_relevance(self, note: ParsedNote, search_terms: Dict[str, List[str]],
                                  insights: SessionInsights, session_context: Dict[str, Any]) -> tuple[float, List[str]]:
        """Calculate relevance score using hybrid matching strategy."""

        score = 0.0
        match_reasons = []

        # Weights for different matching types
        weights = {
            "title_match": 0.4,
            "tag_match": 0.3,
            "content_keyword": 0.2,
            "file_overlap": 0.3,
            "temporal_bonus": 0.1
        }

        note_content_lower = note.content.lower()
        note_title_lower = note.title.lower()
        note_tags_lower = [tag.lower() for tag in note.tags]

        # 1. Title matching
        for topic in search_terms["topics"]:
            if topic in note_title_lower:
                score += weights["title_match"]
                match_reasons.append("title_match")
                break

        for keyword in search_terms["keywords"][:5]:  # Top 5 keywords
            if keyword in note_title_lower:
                score += weights["title_match"] * 0.5
                match_reasons.append("title_keyword")
                break

        # 2. Tag matching
        for topic in search_terms["topics"]:
            if any(topic in tag for tag in note_tags_lower):
                score += weights["tag_match"]
                match_reasons.append("tag_match")

        # 3. Content keyword matching
        keyword_matches = 0
        for keyword in search_terms["keywords"][:10]:
            if keyword in note_content_lower:
                keyword_matches += 1

        if keyword_matches > 0:
            keyword_score = min(keyword_matches / 10.0, 1.0) * weights["content_keyword"]
            score += keyword_score
            match_reasons.append("content_keywords")

        # 4. File name overlap
        for file_name in search_terms["files"]:
            if file_name.lower() in note_content_lower or file_name.lower() in note_title_lower:
                score += weights["file_overlap"]
                match_reasons.append("file_overlap")

        # 5. Temporal relevance (recent notes get slight boost)
        if note.updated_at:
            days_ago = (datetime.now(timezone.utc) - note.updated_at).days
            if days_ago <= 7:
                score += weights["temporal_bonus"] * (7 - days_ago) / 7
                match_reasons.append("recent_modification")

        # 6. Theme matching (high value)
        for theme in search_terms["theme"]:
            if theme in note_title_lower or theme in note_content_lower:
                score += 0.3
                match_reasons.append("theme_match")

        return min(score, 1.0), list(set(match_reasons))

    def _format_note_content(self, note: ParsedNote) -> str:
        """Format note content for context inclusion."""

        # Remove frontmatter
        content = note.content
        frontmatter_match = re.match(r'^---\s*\n.*?\n---\s*\n', content, re.DOTALL)
        if frontmatter_match:
            content = content[frontmatter_match.end():]

        # Limit content length and add metadata
        max_chars = 1000
        if len(content) > max_chars:
            content = content[:max_chars] + "..."

        formatted = f"# {note.title}\n"
        if note.tags:
            formatted += f"Tags: {', '.join(note.tags)}\n"
        formatted += f"Updated: {note.updated_at.strftime('%Y-%m-%d') if note.updated_at else 'Unknown'}\n\n"
        formatted += content

        return formatted