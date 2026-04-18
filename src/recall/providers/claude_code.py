import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from recall.models import ParsedSession, ParsedMessage, ToolCall
from .base import BaseProvider

class ClaudeCodeProvider(BaseProvider):
    """Extract Claude Code sessions from ~/.claude/projects/<encoded_path>/*.jsonl"""

    def __init__(self):
        self.projects_dir = Path.home() / ".claude" / "projects"

    def discover(self, date_range: Optional[Dict[str, datetime]] = None, project_filter: Optional[str] = None) -> List[str]:
        """Discover JSONL session files."""
        if not self.projects_dir.exists():
            return []

        session_files = []

        for project_dir in self.projects_dir.iterdir():
            if not project_dir.is_dir():
                continue

            if project_filter:
                if project_filter.lower() not in project_dir.name.lower():
                    continue

            for jsonl_file in project_dir.glob("*.jsonl"):
                if date_range:
                    mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=timezone.utc)
                    if mtime < date_range['start']:
                        continue
                session_files.append(str(jsonl_file))

        return session_files

    def parse(self, filepath: str) -> Optional[ParsedSession]:
        """Parse Claude Code JSONL session."""
        try:
            messages = []
            session_id = Path(filepath).stem
            started_at = None

            with open(filepath) as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if obj.get("sessionId"):
                        session_id = obj["sessionId"]

                    if obj.get("type") == "user":
                        content = self._extract_text(
                            obj.get("message", {}).get("content", "")
                        )
                        if content and len(content) >= 5:
                            messages.append(ParsedMessage(
                                id=f"claude-{len(messages)}",
                                session_id=session_id,
                                type="user",
                                content=self._clean_content(content),
                                timestamp=self._parse_ts(obj.get("timestamp"))
                            ))

                    elif obj.get("type") == "assistant":
                        content_blocks = obj.get("message", {}).get("content", [])
                        text_content = ""
                        tool_calls = []

                        if isinstance(content_blocks, list):
                            for block in content_blocks:
                                if isinstance(block, dict):
                                    if block.get("type") == "text":
                                        text_content = block.get("text", "")
                                    elif block.get("type") == "tool_use":
                                        tool_calls.append(ToolCall(
                                            id=block.get("id", ""),
                                            name=block.get("name", ""),
                                            input=block.get("input", {})
                                        ))

                        messages.append(ParsedMessage(
                            id=f"claude-{len(messages)}",
                            session_id=session_id,
                            type="assistant",
                            content=text_content,
                            tool_calls=tool_calls,
                            timestamp=self._parse_ts(obj.get("timestamp"))
                        ))

                    if not started_at and obj.get("timestamp"):
                        started_at = self._parse_ts(obj["timestamp"])

            if not messages:
                return None

            user_count = sum(1 for m in messages if m.type == "user")
            asst_count = sum(1 for m in messages if m.type == "assistant")
            tool_count = sum(len(m.tool_calls) for m in messages)

            # Extract project path from encoded directory name
            project_dir = Path(filepath).parent.name
            project_path = project_dir.replace("-", "/")

            return ParsedSession(
                id=session_id,
                project_path=project_path,
                project_name=Path(project_path).name if project_path else "unknown",
                started_at=started_at,
                ended_at=messages[-1].timestamp if messages else started_at,
                message_count=len(messages),
                user_message_count=user_count,
                assistant_message_count=asst_count,
                tool_call_count=tool_count,
                source_tool="claude-code",
                messages=messages
            )

        except (IOError, json.JSONDecodeError) as e:
            print(f"  [claude] Parse error {filepath}: {e}")
            return None

    def _extract_text(self, content: Any) -> str:
        """Extract text from various content formats."""
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            return "\n".join(parts)
        return ""

    def _clean_content(self, text: str) -> str:
        """Remove system tags from content."""
        patterns = [
            r"<system-reminder>.*?</system-reminder>",
            r"<local-command-caveat>.*?</local-command-caveat>",
            r"<local-command-stdout>.*?</local-command-stdout>",
            r"<command-name>.*?</command-name>\s*<command-message>.*?</command-message>",
            r"<task-notification>.*?</task-notification>",
            r"<teammate-message[^>]*>.*?</teammate-message>",
        ]
        for pat in patterns:
            text = re.sub(pat, "", text, flags=re.DOTALL)
        return text.strip()

    def _parse_ts(self, ts: Any) -> Optional[datetime]:
        """Parse timestamp."""
        if not ts:
            return None
        if isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                pass
        return None
