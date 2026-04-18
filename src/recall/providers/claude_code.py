import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from recall.models import ParsedSession, ParsedMessage, ToolCall, ToolResult
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
                    try:
                        mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=timezone.utc)
                        if mtime < date_range['start']:
                            continue
                    except (OSError, ValueError):
                        continue
                session_files.append(str(jsonl_file))

        return session_files

    def parse(self, filepath: str) -> Optional[ParsedSession]:
        """Parse Claude Code JSONL session."""
        try:
            messages = []
            session_id = Path(filepath).stem
            started_at = None
            git_branch = None
            claude_version = None

            with open(filepath) as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if obj.get("sessionId"):
                        session_id = obj["sessionId"]
                    
                    if obj.get("gitBranch"):
                        git_branch = obj["gitBranch"]
                    
                    if obj.get("version"):
                        claude_version = obj["version"]

                    if obj.get("type") == "user":
                        content_blocks = obj.get("message", {}).get("content", "")
                        text_content = ""
                        tool_results = []

                        if isinstance(content_blocks, str):
                            text_content = content_blocks
                        elif isinstance(content_blocks, list):
                            for block in content_blocks:
                                if isinstance(block, dict):
                                    if block.get("type") == "text":
                                        text_content += block.get("text", "") + "\n"
                                    elif block.get("type") == "tool_result":
                                        tool_results.append(ToolResult(
                                            tool_use_id=block.get("tool_use_id", ""),
                                            output=str(block.get("content", ""))
                                        ))
                                elif isinstance(block, str):
                                    text_content += block + "\n"
                        
                        text_content = self._clean_content(text_content.strip())
                        
                        # Add message if it has EITHER content OR tool results
                        if text_content or tool_results:
                            messages.append(ParsedMessage(
                                id=f"claude-{len(messages)}",
                                session_id=session_id,
                                type="user",
                                content=text_content,
                                tool_results=tool_results,
                                timestamp=self._parse_ts(obj.get("timestamp"))
                            ))

                    elif obj.get("type") == "assistant":
                        content_blocks = obj.get("message", {}).get("content", [])
                        text_content = ""
                        thinking = ""
                        tool_calls = []

                        if isinstance(content_blocks, list):
                            for block in content_blocks:
                                if isinstance(block, dict):
                                    btype = block.get("type")
                                    if btype == "text":
                                        text_content += block.get("text", "") + "\n"
                                    elif btype == "thinking":
                                        thinking += block.get("thinking", "") + "\n"
                                    elif btype == "tool_use":
                                        tool_calls.append(ToolCall(
                                            id=block.get("id", ""),
                                            name=block.get("name", ""),
                                            input=block.get("input", {})
                                        ))
                        
                        text_content = text_content.strip()
                        thinking = thinking.strip()

                        if text_content or thinking or tool_calls:
                            messages.append(ParsedMessage(
                                id=f"claude-{len(messages)}",
                                session_id=session_id,
                                type="assistant",
                                content=text_content,
                                thinking=thinking if thinking else None,
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
            # The project-encoded directory is always directly under ~/.claude/projects/
            project_path = "unknown"
            try:
                parts = Path(filepath).parts
                if "projects" in parts:
                    idx = parts.index("projects")
                    if idx + 1 < len(parts):
                        encoded_dir = parts[idx + 1]
                        project_path = encoded_dir.replace("-", "/")
                        if project_path.startswith("home/"):
                            project_path = "/" + project_path
            except Exception:
                pass

            return ParsedSession(
                id=session_id,
                project_path=project_path,
                project_name=Path(project_path).name if project_path != "unknown" else "unknown",
                started_at=started_at,
                ended_at=messages[-1].timestamp if messages else started_at,
                message_count=len(messages),
                user_message_count=user_count,
                assistant_message_count=asst_count,
                tool_call_count=tool_count,
                source_tool="claude-code",
                git_branch=git_branch,
                claude_version=claude_version,
                messages=messages
            )

        except (IOError, json.JSONDecodeError) as e:
            print(f"  [claude] Parse error {filepath}: {e}")
            return None

    def _extract_text(self, content: Any) -> str:
        # Keep for backward compatibility if needed, but we use inline logic now
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
        """Remove redundant system tags from content while preserving context."""
        patterns = [
            r"<system-reminder>.*?</system-reminder>",
            r"<local-command-caveat>.*?</local-command-caveat>",
            # We preserve <local-command-stdout> and <command-message> as they contain valuable work context
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
