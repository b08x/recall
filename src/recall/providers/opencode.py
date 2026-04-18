import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from recall.models import ParsedSession, ParsedMessage, ToolCall
from .base import BaseProvider

class OpenCodeProvider(BaseProvider):
    """Extract OpenCode sessions from ~/.local/share/opencode/opencode.db"""

    def __init__(self):
        self.db_path = Path.home() / ".local" / "share" / "opencode" / "opencode.db"

    def discover(self, date_range: Optional[Dict[str, datetime]] = None, project_filter: Optional[str] = None) -> List[str]:
        """Discover sessions via SQLite query."""
        if not self.db_path.exists():
            return []

        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            # time_created in OpenCode is in milliseconds
            query = "SELECT id FROM session"
            params = []
            
            if date_range:
                query += " WHERE time_created >= ?"
                params.append(int(date_range['start'].timestamp() * 1000))
            
            query += " ORDER BY time_created DESC"
            
            cursor = conn.execute(query, params)
            virtual_paths = [f"{self.db_path}#{row[0]}" for row in cursor.fetchall()]
            conn.close()
            return virtual_paths

        except sqlite3.Error:
            return []

    def parse(self, virtual_path: str) -> Optional[ParsedSession]:
        """Parse OpenCode session from SQLite."""
        if "#" not in virtual_path:
            return None

        db_path, session_id = virtual_path.rsplit("#", 1)

        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row

            # Get session
            cursor = conn.execute(
                """SELECT id, project_id, slug, title, directory,
                          time_created, time_updated
                   FROM session WHERE id = ?""",
                (session_id,)
            )
            session_row = cursor.fetchone()
            if not session_row:
                conn.close()
                return None

            # Get messages (time_created is in MILLISECONDS)
            cursor = conn.execute(
                """SELECT id, data, time_created
                   FROM message
                   WHERE session_id = ?
                   ORDER BY time_created ASC""",
                (session_id,)
            )
            message_rows = cursor.fetchall()

            messages = []
            for row in message_rows:
                try:
                    data = json.loads(row["data"])
                    role = data.get("role", "unknown")

                    messages.append(ParsedMessage(
                        id=str(row["id"]),
                        session_id=session_id,
                        type=role if role in ["user", "assistant"] else "system",
                        content=self._extract_content(data),
                        tool_calls=self._extract_tools(data),
                        timestamp=datetime.fromtimestamp(
                            row["time_created"] / 1000, tz=timezone.utc
                        )
                    ))
                except json.JSONDecodeError:
                    continue

            conn.close()

            started = datetime.fromtimestamp(
                session_row["time_created"] / 1000, tz=timezone.utc
            )

            return ParsedSession(
                id=session_id,
                project_path=session_row["directory"] or "",
                project_name=session_row["title"] or session_row["slug"] or "opencode-session",
                started_at=started,
                ended_at=datetime.fromtimestamp(
                    session_row["time_updated"] / 1000, tz=timezone.utc
                ) if session_row["time_updated"] else started,
                message_count=len(messages),
                user_message_count=sum(1 for m in messages if m.type == "user"),
                assistant_message_count=sum(1 for m in messages if m.type == "assistant"),
                tool_call_count=sum(len(m.tool_calls) for m in messages),
                source_tool="opencode",
                messages=messages
            )

        except sqlite3.Error as e:
            print(f"  [opencode] Parse error: {e}")
            return None

    def _extract_content(self, data: Dict) -> str:
        """Extract content from message data."""
        content = data.get("content", "")
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "\n".join(parts)
        return ""

    def _extract_tools(self, data: Dict) -> List[ToolCall]:
        """Extract tool calls from message data."""
        calls = []
        content = data.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    calls.append(ToolCall(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        input=block.get("input", {})
                    ))
        return calls
