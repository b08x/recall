from datetime import datetime, timedelta
from typing import List, Dict, Any
from recall.models import ParsedMessage, ParsedSession

class ContextualChunker:
    """Intelligently chunks session messages based on time and semantic boundaries."""

    def __init__(self, 
                 max_chunk_chars: int = 8000, 
                 time_gap_minutes: int = 30):
        self.max_chunk_chars = max_chunk_chars
        self.time_gap_threshold = timedelta(minutes=time_gap_minutes)

    def chunk_session(self, session: ParsedSession) -> List[str]:
        """Split a session into a list of text chunks for analysis."""
        if not session.messages:
            return []

        chunks = []
        current_messages = []
        current_length = 0
        last_timestamp = None

        for msg in session.messages:
            msg_text = self._format_message(msg)
            msg_len = len(msg_text)
            
            # 1. Temporal Boundary Check
            time_split = False
            if last_timestamp and msg.timestamp:
                if msg.timestamp - last_timestamp > self.time_gap_threshold:
                    time_split = True
            
            # 2. Length Boundary Check
            # We split if we exceed max_chunk_chars. 
            # We prefer splitting on User messages, but if a single message is huge, we must split.
            length_split = False
            if current_length + msg_len > self.max_chunk_chars:
                if msg.type == 'user' or current_length > self.max_chunk_chars * 0.8:
                    length_split = True

            # If we need to split, save the current chunk
            if (time_split or length_split) and current_messages:
                chunks.append("\n".join(current_messages))
                current_messages = []
                current_length = 0

            # If the single message is STILL larger than max_chunk_chars on its own,
            # we must truncate or sub-chunk it to avoid downstream errors.
            if msg_len > self.max_chunk_chars:
                # If we have current_messages, flush them first
                if current_messages:
                    chunks.append("\n".join(current_messages))
                    current_messages = []
                    current_length = 0
                
                # Sub-chunk the giant message
                for i in range(0, msg_len, self.max_chunk_chars):
                    sub_text = msg_text[i:i + self.max_chunk_chars]
                    chunks.append(f"[TRUNCATED_PART_{i//self.max_chunk_chars}] {sub_text}")
                continue

            current_messages.append(msg_text)
            current_length += msg_len
            if msg.timestamp:
                last_timestamp = msg.timestamp

        # Add the final chunk
        if current_messages:
            chunks.append("\n".join(current_messages))

        return chunks

    def _format_message(self, msg: ParsedMessage) -> str:
        """Format a single message for the LLM context."""
        header = f"[{msg.type.upper()}]"
        if msg.timestamp:
            header += f" {msg.timestamp.strftime('%H:%M:%S')}"
        
        body = msg.content
        if msg.thinking:
            body = f"<thinking>\n{msg.thinking}\n</thinking>\n{body}"
        
        # Add summary of tool calls/results if present
        if msg.tool_calls:
            calls = "\n".join([f"Tool Call: {tc.name}({tc.input})" for tc in msg.tool_calls])
            body += f"\n{calls}"
        
        if msg.tool_results:
            results = "\n".join([f"Tool Result: {tr.output[:200]}..." for tr in msg.tool_results])
            body += f"\n{results}"

        return f"{header}\n{body}\n"
