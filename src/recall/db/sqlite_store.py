import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from recall.models import ParsedSession, ParsedMessage, ToolCall, ToolResult, SessionUsage, SessionAnalysis, CorrelationResult

class SQLiteStore:
    """Handles persistence of sessions, messages, and analysis results in SQLite."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initialize the database schema."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    project_name TEXT,
                    project_path TEXT,
                    summary TEXT,
                    generated_title TEXT,
                    started_at DATETIME,
                    ended_at DATETIME,
                    message_count INTEGER DEFAULT 0,
                    git_branch TEXT,
                    source_tool TEXT DEFAULT 'unknown',
                    metadata TEXT
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
                    type TEXT CHECK(type IN ('user', 'assistant', 'system')),
                    content TEXT,
                    thinking TEXT,
                    timestamp DATETIME,
                    parent_id TEXT,
                    usage TEXT
                );

                CREATE TABLE IF NOT EXISTS tool_calls (
                    id TEXT PRIMARY KEY,
                    message_id TEXT REFERENCES messages(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    input TEXT
                );

                CREATE TABLE IF NOT EXISTS topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                );

                CREATE TABLE IF NOT EXISTS file_paths (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL
                );

                CREATE TABLE IF NOT EXISTS session_analysis (
                    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
                    key_actions TEXT,
                    analyzed_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS session_topics (
                    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
                    topic_id INTEGER REFERENCES topics(id),
                    PRIMARY KEY (session_id, topic_id)
                );

                CREATE TABLE IF NOT EXISTS session_files (
                    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
                    file_id INTEGER REFERENCES file_paths(id),
                    PRIMARY KEY (session_id, file_id)
                );

                CREATE TABLE IF NOT EXISTS correlations (
                    id TEXT PRIMARY KEY,
                    start_date DATETIME,
                    end_date DATETIME,
                    narrative TEXT,
                    workstreams TEXT,
                    next_actions TEXT,
                    one_thing TEXT,
                    one_thing_reasoning TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS correlation_sessions (
                    correlation_id TEXT REFERENCES correlations(id) ON DELETE CASCADE,
                    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
                    PRIMARY KEY (correlation_id, session_id)
                );
            """)

    def save_session(self, session: ParsedSession):
        """Save or update a session and its messages."""
        with self._get_connection() as conn:
            # Save session
            conn.execute("""
                INSERT OR REPLACE INTO sessions (
                    id, platform, project_name, project_path, summary, generated_title,
                    started_at, ended_at, message_count, git_branch, source_tool, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session.id, session.source_tool, session.project_name, session.project_path,
                json.dumps(session.summary) if session.summary else None,
                session.generated_title,
                session.started_at.isoformat() if session.started_at else None,
                session.ended_at.isoformat() if session.ended_at else None,
                session.message_count, session.git_branch, session.source_tool,
                json.dumps({"claude_version": session.claude_version}) if session.claude_version else None
            ))

            # Save messages
            for msg in session.messages:
                conn.execute("""
                    INSERT OR REPLACE INTO messages (
                        id, session_id, type, content, thinking, timestamp, parent_id, usage
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    msg.id, session.id, msg.type, msg.content, msg.thinking,
                    msg.timestamp.isoformat() if msg.timestamp else None,
                    msg.parent_id,
                    json.dumps(msg.usage) if msg.usage else None
                ))

                # Save tool calls
                for tc in msg.tool_calls:
                    conn.execute("""
                        INSERT OR REPLACE INTO tool_calls (id, message_id, name, input)
                        VALUES (?, ?, ?, ?)
                    """, (tc.id, msg.id, tc.name, json.dumps(tc.input)))

    def save_analysis(self, analysis: SessionAnalysis):
        """Save session topics, files, and actions."""
        with self._get_connection() as conn:
            # Save base analysis
            conn.execute("""
                INSERT OR REPLACE INTO session_analysis (session_id, key_actions)
                VALUES (?, ?)
            """, (analysis.session_id, json.dumps(analysis.key_actions)))

            # Save topics (normalized)
            for topic in analysis.topics:
                conn.execute("INSERT OR IGNORE INTO topics (name) VALUES (?)", (topic,))
                conn.execute("""
                    INSERT OR IGNORE INTO session_topics (session_id, topic_id)
                    SELECT ?, id FROM topics WHERE name = ?
                """, (analysis.session_id, topic))

            # Save files (normalized)
            for path in analysis.files_touched:
                conn.execute("INSERT OR IGNORE INTO file_paths (path) VALUES (?)", (path,))
                conn.execute("""
                    INSERT OR IGNORE INTO session_files (session_id, file_id)
                    SELECT ?, id FROM file_paths WHERE path = ?
                """, (analysis.session_id, path))

    def save_correlation(self, result: CorrelationResult):
        """Save cross-session synthesis result."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO correlations (
                    id, start_date, end_date, narrative, workstreams, next_actions,
                    one_thing, one_thing_reasoning
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.id,
                result.start_date.isoformat(),
                result.end_date.isoformat(),
                result.narrative,
                json.dumps(result.workstreams),
                json.dumps(result.next_actions),
                result.one_thing,
                result.one_thing_reasoning
            ))

            for session_id in result.session_ids:
                conn.execute("""
                    INSERT OR IGNORE INTO correlation_sessions (correlation_id, session_id)
                    VALUES (?, ?)
                """, (result.id, session_id))

    def get_session(self, session_id: str) -> Optional[ParsedSession]:
        """Retrieve a full session with messages."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not row:
                return None
            
            # This is a simplified reconstruction for brevity
            # In a real impl, we'd rebuild the full nested dataclass structure
            return row # Returning raw row for now to keep the example concise

    def get_analysis(self, session_id: str) -> Optional[SessionAnalysis]:
        """Retrieve saved analysis for a session."""
        with self._get_connection() as conn:
            # 1. Get base analysis
            row = conn.execute(
                "SELECT key_actions, analyzed_at FROM session_analysis WHERE session_id = ?", 
                (session_id,)
            ).fetchone()
            if not row:
                return None
            
            analyzed_at = datetime.fromisoformat(row['analyzed_at']) if isinstance(row['analyzed_at'], str) else row['analyzed_at']
            key_actions = json.loads(row['key_actions']) if row['key_actions'] else []

            # 2. Get topics
            topics = []
            topic_rows = conn.execute("""
                SELECT t.name FROM topics t
                JOIN session_topics st ON t.id = st.topic_id
                WHERE st.session_id = ?
            """, (session_id,)).fetchall()
            topics = [r['name'] for r in topic_rows]

            # 3. Get files
            files = []
            file_rows = conn.execute("""
                SELECT f.path FROM file_paths f
                JOIN session_files sf ON f.id = sf.file_id
                WHERE sf.session_id = ?
            """, (session_id,)).fetchall()
            files = [r['path'] for r in file_rows]

            return SessionAnalysis(
                session_id=session_id,
                topics=topics,
                files_touched=files,
                key_actions=key_actions,
                analyzed_at=analyzed_at
            )
