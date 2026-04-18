import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from recall.models import ParsedSession, ParsedMessage, ToolCall, ToolResult, SessionUsage
from .base import BaseProvider

class GeminiProvider(BaseProvider):
    """Extract Gemini CLI sessions from ~/.gemini/tmp/<hash>/chats/*.json"""

    def __init__(self):
        self.home_dir = Path.home() / ".gemini"
        self.tmp_dir = self.home_dir / "tmp"
        self.projects_file = self.home_dir / "projects.json"

    def discover(self, date_range: Optional[Dict[str, datetime]] = None, project_filter: Optional[str] = None) -> List[str]:
        """Discover session files using correct Gemini path structure."""
        if not self.tmp_dir.exists():
            return []

        # Load project mappings (hash -> name)
        project_mappings = {}
        if self.projects_file.exists():
            try:
                with open(self.projects_file) as f:
                    data = json.load(f)
                    project_mappings = data.get("projects", {})
            except (json.JSONDecodeError, IOError):
                pass

        session_files = []

        # Scan tmp/<project_hash>/chats/*.json
        for entry in self.tmp_dir.iterdir():
            if not entry.is_dir():
                continue

            chats_dir = entry / "chats"
            if not chats_dir.exists():
                continue

            # Check project filter
            project_name = project_mappings.get(entry.name, entry.name)
            if project_filter:
                if project_filter.lower() not in project_name.lower() and \
                   project_filter.lower() not in entry.name.lower():
                    continue

            # Collect JSON files
            for json_file in chats_dir.glob("*.json"):
                # Fast check for modification time if date_range provided
                if date_range:
                    mtime = datetime.fromtimestamp(json_file.stat().st_mtime, tz=timezone.utc)
                    if mtime < date_range['start']:
                        continue
                
                session_files.append(str(json_file))

        return session_files

    def parse(self, filepath: str) -> Optional[ParsedSession]:
        """Parse Gemini session JSON into normalized schema."""
        try:
            with open(filepath) as f:
                data = json.load(f)

            if not data.get("sessionId") or not data.get("messages"):
                return None

            # Resolve project info
            project_dir = Path(filepath).parent.parent
            project_id = project_dir.name

            project_path = ""
            project_name = project_id

            root_file = project_dir / ".project_root"
            if root_file.exists():
                project_path = root_file.read_text().strip()
                project_name = Path(project_path).name

            # Parse messages
            messages = []
            user_count = 0
            assistant_count = 0
            tool_count = 0

            for msg in data["messages"]:
                if msg.get("type") == "info":
                    continue

                msg_type = self._normalize_type(msg["type"])
                content = self._extract_content(msg)
                thinking = self._extract_thinking(msg)

                # Extract tool calls
                tool_calls = []
                for tc in msg.get("toolCalls", []):
                    tool_calls.append(ToolCall(
                        id=tc.get("id", ""),
                        name=tc.get("name", ""),
                        input=tc.get("args", {})
                    ))

                tool_results = self._extract_tool_results(msg)
                
                # Only add message if it has some meaningful content
                if content or thinking or tool_calls or tool_results:
                    if msg_type == "user":
                        user_count += 1
                    elif msg_type == "assistant":
                        assistant_count += 1
                    
                    tool_count += len(tool_calls)

                    messages.append(ParsedMessage(
                        id=msg.get("id", ""),
                        session_id=data["sessionId"],
                        type=msg_type,
                        content=content,
                        thinking=thinking,
                        tool_calls=tool_calls,
                        tool_results=tool_results,
                        usage=self._extract_usage(msg),
                        timestamp=self._parse_timestamp(msg.get("timestamp"))
                    ))

            if not messages:
                return None

            # Calculate usage
            usage = self._calculate_usage(messages, data)

            return ParsedSession(
                id=data["sessionId"],
                project_path=project_path,
                project_name=project_name,
                started_at=self._parse_timestamp(data.get("startTime")),
                ended_at=self._parse_timestamp(data.get("lastUpdated")),
                message_count=len(messages),
                user_message_count=user_count,
                assistant_message_count=assistant_count,
                tool_call_count=tool_count,
                source_tool="gemini-cli",
                usage=usage,
                messages=messages
            )

        except (json.JSONDecodeError, IOError, KeyError) as e:
            print(f"  [gemini] Parse error {filepath}: {e}")
            return None

    def _normalize_type(self, msg_type: str) -> str:
        """Normalize Gemini message types."""
        mapping = {
            "gemini": "assistant",
            "user": "user",
            "info": "system"
        }
        return mapping.get(msg_type, "system")

    def _extract_content(self, msg: Dict) -> str:
        """Extract text content from various formats."""
        content = msg.get("content", "")

        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif "text" in block:
                        parts.append(block["text"])
                elif isinstance(block, str):
                    parts.append(block)
            return "\n".join(parts)

        return ""

    def _extract_thinking(self, msg: Dict) -> Optional[str]:
        """Extract thinking/reasoning content."""
        return msg.get("thinking") or msg.get("reasoning")

    def _extract_tool_results(self, msg: Dict) -> List[ToolResult]:
        """Extract tool results."""
        results = []
        for tr in msg.get("toolResults", []):
            results.append(ToolResult(
                tool_use_id=tr.get("toolUseId", ""),
                output=str(tr.get("output", ""))
            ))
        return results

    def _extract_usage(self, msg: Dict) -> Optional[Dict]:
        """Extract token usage."""
        tokens = msg.get("tokens", {})
        if tokens:
            return {
                "inputTokens": tokens.get("input", 0),
                "outputTokens": tokens.get("output", 0),
                "model": tokens.get("model", "unknown")
            }
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

    def _calculate_usage(self, messages: List[ParsedMessage], data: Dict) -> SessionUsage:
        """Calculate total usage from messages or session-level data."""
        total_in = sum(
            (m.usage or {}).get("inputTokens", 0) for m in messages
        )
        total_out = sum(
            (m.usage or {}).get("outputTokens", 0) for m in messages
        )

        models = list(set(
            (m.usage or {}).get("model") for m in messages if m.usage
        ))

        return SessionUsage(
            total_input_tokens=total_in,
            total_output_tokens=total_out,
            models_used=models or ["gemini"],
            primary_model=models[0] if models else "gemini"
        )
