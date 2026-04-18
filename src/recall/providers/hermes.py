import json
import sqlite3
import glob
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from recall.models import ParsedSession, ParsedMessage, ToolCall, ToolResult, SessionUsage
from .base import BaseProvider

class HermesProvider(BaseProvider):
    """Extract Hermes Agent sessions from ~/.hermes/state.db (SQLite) and JSON files."""

    def __init__(self):
        self.hermes_dir = Path.home() / ".hermes"
        self.db_path = self.hermes_dir / "state.db"
        self.sessions_dirs = [
            self.hermes_dir / "sessions",
            self.hermes_dir / "profiles" / "*" / "sessions"
        ]

    def discover(self, date_range: Optional[Dict[str, datetime]] = None, project_filter: Optional[str] = None) -> List[str]:
        """Discover sessions via direct SQLite query and JSON files."""
        all_paths = []

        # 1. Discover SQLite sessions
        if self.db_path.exists():
            try:
                conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
                cursor = conn.execute("SELECT id, title FROM sessions")
                for row in cursor.fetchall():
                    session_id, title = row
                    if project_filter and title:
                        if project_filter.lower() not in title.lower():
                            continue
                    all_paths.append(f"{self.db_path}#{session_id}")
                conn.close()
            except sqlite3.Error as e:
                print(f"  [hermes] SQLite error: {e}")

        # 2. Discover JSON sessions
        for sessions_dir in self.sessions_dirs:
            # Expand glob for profiles
            for dir_path in glob.glob(str(sessions_dir)):
                p = Path(dir_path)
                if not p.exists():
                    continue
                for json_file in p.glob("session_*.json"):
                    if date_range:
                        mtime = datetime.fromtimestamp(json_file.stat().st_mtime, tz=timezone.utc)
                        if mtime < date_range['start']:
                            continue
                    all_paths.append(str(json_file))

        return all_paths

    def parse(self, filepath: str) -> Optional[ParsedSession]:
        """Parse session from SQLite virtual path or JSON file."""
        if "#" in filepath:
            return self._parse_sqlite(filepath)
        elif filepath.endswith(".json"):
            return self._parse_json(filepath)
        return None

    def _parse_sqlite(self, virtual_path: str) -> Optional[ParsedSession]:
        """Parse session from SQLite using virtual path format."""
        db_path, session_id = virtual_path.rsplit("#", 1)

        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row

            # Get session metadata
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            )
            session_row = cursor.fetchone()
            if not session_row:
                conn.close()
                return None

            # Get messages
            cursor = conn.execute(
                """SELECT * FROM messages
                   WHERE session_id = ?
                   ORDER BY timestamp ASC""",
                (session_id,)
            )
            message_rows = cursor.fetchall()

            # Parse messages
            messages = []
            user_count = 0
            assistant_count = 0
            tool_count = 0

            for row_raw in message_rows:
                msg_dict = {k: row_raw[k] for k in row_raw.keys()}
                role = msg_dict["role"]

                # Handle tool results - attach to previous assistant
                if role == "tool":
                    last_asst = None
                    for m in reversed(messages):
                        if m.type == "assistant":
                            last_asst = m
                            break

                    if last_asst:
                        last_asst.tool_results.append(ToolResult(
                            tool_use_id=msg_dict.get("tool_call_id") or f"tool-{msg_dict['id']}",
                            output=msg_dict.get("content") or ""
                        ))
                    continue

                msg_type = "assistant" if role == "assistant" else "user"

                # Extract tool calls (if any)
                tool_calls = []
                if msg_type == "assistant" and msg_dict.get("tool_calls"):
                    try:
                        tc_data_list = json.loads(msg_dict["tool_calls"])
                        for tc_data in tc_data_list:
                            tool_calls.append(ToolCall(
                                id=tc_data.get("id", ""),
                                name=tc_data.get("function", {}).get("name") or tc_data.get("name", ""),
                                input=tc_data.get("function", {}).get("arguments") or tc_data.get("args") or {}
                            ))
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Only add message if it has meaningful content
                if msg_dict["content"] or msg_dict["reasoning"] or tool_calls:
                    if msg_type == "user":
                        user_count += 1
                    else:
                        assistant_count += 1
                    
                    tool_count += len(tool_calls)

                    # Get timestamp if available
                    timestamp = None
                    if msg_dict.get("timestamp"):
                        try:
                            timestamp = datetime.fromtimestamp(msg_dict["timestamp"], tz=timezone.utc)
                        except (ValueError, TypeError):
                            pass

                    messages.append(ParsedMessage(
                        id=f"hermes-{msg_dict['id']}",
                        session_id=f"hermes-agent:{session_id}",
                        type=msg_type,
                        content=msg_dict["content"] or "",
                        thinking=msg_dict["reasoning"],
                        tool_calls=tool_calls,
                        tool_results=[],
                        usage={
                            "outputTokens": msg_dict["token_count"] or 0,
                            "model": session_row["model"] or "unknown"
                        } if msg_dict["token_count"] else None,
                        timestamp=timestamp
                    ))

            # Build usage from session-level data
            usage = SessionUsage(
                total_input_tokens=session_row["input_tokens"] or 0,
                total_output_tokens=session_row["output_tokens"] or 0,
                cache_creation_tokens=session_row["cache_write_tokens"] or 0,
                cache_read_tokens=session_row["cache_read_tokens"] or 0,
                estimated_cost_usd=session_row["actual_cost_usd"] or
                                    session_row["estimated_cost_usd"] or 0,
                models_used=[session_row["model"]] if session_row["model"] else [],
                primary_model=session_row["model"] or "unknown"
            )

            started = datetime.fromtimestamp(
                session_row["started_at"], tz=timezone.utc
            ) if session_row["started_at"] else None
            ended = datetime.fromtimestamp(
                session_row["ended_at"], tz=timezone.utc
            ) if session_row["ended_at"] else started

            conn.close()

            return ParsedSession(
                id=f"hermes-agent:{session_id}",
                project_path="",  # Hermes sessions are global
                project_name=session_row["title"] or "hermes-agent-session",
                generated_title=session_row["title"],
                title_source="insight" if session_row["title"] else None,
                started_at=started,
                ended_at=ended,
                message_count=len(messages),
                user_message_count=user_count,
                assistant_message_count=assistant_count,
                tool_call_count=tool_count,
                source_tool="hermes-agent",
                usage=usage,
                messages=messages
            )
        except sqlite3.Error as e:
            print(f"  [hermes] Parse error for {session_id}: {e}")
            return None

    def _parse_json(self, filepath: str) -> Optional[ParsedSession]:
        """Parse session from Hermes JSON file."""
        try:
            with open(filepath) as f:
                data = json.load(f)

            if not data.get("session_id"):
                return None

            session_id = data["session_id"]
            model = data.get("model", "unknown")

            # Parse messages
            messages = []
            user_count = 0
            assistant_count = 0
            tool_count = 0
            total_out = 0

            for msg_data in data.get("messages", []):
                role = msg_data.get("role")
                if role == "tool":
                    # Attach tool result to previous assistant
                    last_asst = None
                    for m in reversed(messages):
                        if m.type == "assistant":
                            last_asst = m
                            break
                    if last_asst:
                        last_asst.tool_results.append(ToolResult(
                            tool_use_id=msg_data.get("tool_call_id") or f"tool-{len(messages)}",
                            output=msg_data.get("content") or ""
                        ))
                    continue

                content = msg_data.get("content") or ""
                thinking = msg_data.get("reasoning")
                msg_type = "assistant" if role == "assistant" else "user"

                # Extract tool calls
                tool_calls = []
                for tc_data in msg_data.get("tool_calls", []):
                    tool_calls.append(ToolCall(
                        id=tc_data.get("id", ""),
                        name=tc_data.get("function", {}).get("name") or tc_data.get("name", ""),
                        input=tc_data.get("function", {}).get("arguments") or tc_data.get("args") or {}
                    ))

                # Only add message if it has meaningful content
                if content or thinking or tool_calls:
                    if msg_type == "user":
                        user_count += 1
                    else:
                        assistant_count += 1
                        total_out += msg_data.get("token_count") or 0
                    
                    tool_count += len(tool_calls)

                    messages.append(ParsedMessage(
                        id=f"hermes-{len(messages)}",
                        session_id=f"hermes-agent:{session_id}",
                        type=msg_type,
                        content=content,
                        thinking=thinking,
                        tool_calls=tool_calls,
                        tool_results=[],
                        usage={
                            "outputTokens": msg_data.get("token_count") or 0,
                            "model": model
                        } if msg_data.get("token_count") else None,
                        timestamp=None # Messages don't have timestamps in JSON
                    ))

            started = self._parse_timestamp(data.get("session_start"))
            ended = self._parse_timestamp(data.get("last_updated")) or started

            usage = SessionUsage(
                primary_model=model,
                models_used=[model] if model else [],
                total_output_tokens=total_out
            )

            # Use session_id as title if none found
            title = data.get("title") or f"hermes-session-{session_id}"

            return ParsedSession(
                id=f"hermes-agent:{session_id}",
                project_path="",
                project_name=title,
                generated_title=title,
                started_at=started,
                ended_at=ended,
                message_count=len(messages),
                user_message_count=user_count,
                assistant_message_count=assistant_count,
                tool_call_count=tool_count,
                source_tool="hermes-agent",
                usage=usage,
                messages=messages
            )
        except Exception as e:
            print(f"  [hermes] Parse error for {filepath}: {e}")
            return None

    def _parse_timestamp(self, ts: Any) -> Optional[datetime]:
        """Parse various timestamp formats."""
        if not ts:
            return None
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                pass
        return None
