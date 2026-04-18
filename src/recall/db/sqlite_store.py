import sqlite3
import json
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import List, Dict, Optional, Any
from recall.models import (
    ParsedSession, ParsedMessage, ToolCall, ToolResult, 
    SessionUsage, SessionAnalysis, CorrelationResult,
    SessionInsight, SessionInsights
)

class SQLiteStore:
    """Handles persistence of sessions, messages, and analysis results in SQLite."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_connection(self):
        """Get or create a thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, timeout=5000)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL;")
        return self._local.conn

    def close(self):
        """Close the thread-local connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

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
                    metadata TEXT,
                    indexing_status TEXT DEFAULT 'pending'
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

                CREATE TABLE IF NOT EXISTS session_insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
                    category TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance REAL DEFAULT 0.5,
                    primary_theme TEXT,
                    confidence REAL,
                    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP
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

                CREATE TABLE IF NOT EXISTS dlq (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    payload TEXT NOT NULL,
                    error TEXT,
                    failed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    retry_count INTEGER DEFAULT 0
                );
            """)

            # Simple migration: Add indexing_status if it doesn't exist
            cursor = conn.execute("PRAGMA table_info(sessions)")
            columns = [row['name'] for row in cursor.fetchall()]
            if 'indexing_status' not in columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN indexing_status TEXT DEFAULT 'pending'")
                conn.commit()

    def save_dlq_item(self, session_id: str, payload: Dict[str, Any], error_msg: str):
        """Save a failed session payload to the Dead Letter Queue table."""
        # Convert non-serializable objects in payload if any
        # The session in payload is a ParsedSession, which needs conversion
        serializable_payload = payload.copy()
        if "session" in serializable_payload and hasattr(serializable_payload["session"], "__dict__"):
            # This is a bit tricky since ParsedSession might have nested objects
            # MultiSourceCorrelator already uses asdict for some parts, but let's be safe
            def make_serializable(obj):
                if is_dataclass(obj):
                    return asdict(obj)
                if isinstance(obj, datetime):
                    return obj.isoformat()
                if isinstance(obj, dict):
                    return {k: make_serializable(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [make_serializable(v) for v in obj]
                return obj
            
            serializable_payload["session"] = make_serializable(serializable_payload["session"])

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO dlq (session_id, payload, error)
                VALUES (?, ?, ?)
            """, (session_id, json.dumps(serializable_payload), error_msg))
            conn.commit()

    def get_dlq_items(self) -> List[Dict[str, Any]]:
        """Retrieve all items from the Dead Letter Queue."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT id, session_id, payload, error, failed_at, retry_count FROM dlq")
            items = []
            for row in cursor.fetchall():
                items.append({
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "payload": json.loads(row["payload"]),
                    "error": row["error"],
                    "failed_at": row["failed_at"],
                    "retry_count": row["retry_count"]
                })
            return items

    def delete_dlq_item(self, dlq_id: int):
        """Remove an item from the Dead Letter Queue."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM dlq WHERE id = ?", (dlq_id,))
            conn.commit()

    def increment_dlq_retry(self, dlq_id: int):
        """Increment the retry count for a DLQ item."""
        with self._get_connection() as conn:
            conn.execute("UPDATE dlq SET retry_count = retry_count + 1 WHERE id = ?", (dlq_id,))
            conn.commit()

    def save_session(self, session: ParsedSession, conn: Optional[sqlite3.Connection] = None):
        """Save or update a session and its messages."""
        should_close = False
        if conn is None:
            conn = self._get_connection()
            should_close = True
        
        try:
            # Save session
            conn.execute("""
                INSERT OR REPLACE INTO sessions (
                    id, platform, project_name, project_path, summary, generated_title,
                    started_at, ended_at, message_count, git_branch, source_tool, metadata,
                    indexing_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session.id, session.source_tool, session.project_name, session.project_path,
                json.dumps(session.summary) if session.summary else None,
                session.generated_title,
                session.started_at.isoformat() if session.started_at else None,
                session.ended_at.isoformat() if session.ended_at else None,
                session.message_count, session.git_branch, session.source_tool,
                json.dumps({"claude_version": session.claude_version}) if session.claude_version else None,
                'pending'
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
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        conn.execute("""
                            INSERT OR REPLACE INTO tool_calls (
                                id, message_id, name, input
                            ) VALUES (?, ?, ?, ?)
                        """, (
                            tc.id, msg.id, tc.name, json.dumps(tc.input) if tc.input else None
                        ))
            
            if should_close:
                conn.commit()
        finally:
            if should_close:
                conn.close()

    def update_indexing_status(self, session_id: str, status: str):
        """Update the indexing status of a session."""
        with self._get_connection() as conn:
            conn.execute("UPDATE sessions SET indexing_status = ? WHERE id = ?", (status, session_id))
            conn.commit()

    def get_failed_indexing_sessions(self) -> List[str]:
        """Find sessions that are marked as 'failed' or are still 'pending'."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT id FROM sessions WHERE indexing_status IN ('failed', 'pending')")
            return [row['id'] for row in cursor.fetchall()]

    def get_analysis(self, session_id: str) -> Optional[SessionAnalysis]:
        """Retrieve saved analysis for a session."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM session_analysis WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            # Fetch topics
            cursor = conn.execute("""
                SELECT t.name FROM topics t
                JOIN session_topics st ON t.id = st.topic_id
                WHERE st.session_id = ?
            """, (session_id,))
            topics = [r['name'] for r in cursor.fetchall()]

            # Fetch files
            cursor = conn.execute("""
                SELECT f.path FROM file_paths f
                JOIN session_files sf ON f.id = sf.file_id
                WHERE sf.session_id = ?
            """, (session_id,))
            files = [r['path'] for r in cursor.fetchall()]

            return SessionAnalysis(
                session_id=session_id,
                topics=topics,
                files_touched=files,
                key_actions=json.loads(row['key_actions']) if row['key_actions'] else []
            )

    def get_insights(self, session_id: str) -> Optional[SessionInsights]:
        """Retrieve saved insights for a session."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM session_insights WHERE session_id = ?", (session_id,))
            rows = cursor.fetchall()
            if not rows:
                return None
            
            insights_list = []
            for row in rows:
                insights_list.append(SessionInsight(
                    category=row['category'],
                    content=row['content'],
                    importance=row['importance'],
                    primary_theme=row['primary_theme'],
                    confidence=row['confidence']
                ))
            
            return SessionInsights(
                session_id=session_id,
                insights=insights_list
            )

    def save_analysis(self, analysis: SessionAnalysis, conn: Optional[sqlite3.Connection] = None):
        """Save session analysis (key actions, topics, files)."""
        should_close = False
        if conn is None:
            conn = self._get_connection()
            should_close = True
        
        try:
            # Save main analysis
            conn.execute("""
                INSERT OR REPLACE INTO session_analysis (session_id, key_actions)
                VALUES (?, ?)
            """, (analysis.session_id, json.dumps(analysis.key_actions)))

            # Save topics and relationships
            for topic_name in analysis.topics:
                conn.execute("INSERT OR IGNORE INTO topics (name) VALUES (?)", (topic_name,))
                cursor = conn.execute("SELECT id FROM topics WHERE name = ?", (topic_name,))
                topic_id = cursor.fetchone()[0]
                conn.execute("""
                    INSERT OR IGNORE INTO session_topics (session_id, topic_id)
                    VALUES (?, ?)
                """, (analysis.session_id, topic_id))

            # Save files and relationships
            for file_path in analysis.files_touched:
                conn.execute("INSERT OR IGNORE INTO file_paths (path) VALUES (?)", (file_path,))
                cursor = conn.execute("SELECT id FROM file_paths WHERE path = ?", (file_path,))
                file_id = cursor.fetchone()[0]
                conn.execute("""
                    INSERT OR IGNORE INTO session_files (session_id, file_id)
                    VALUES (?, ?)
                """, (analysis.session_id, file_id))

            if should_close:
                conn.commit()
        finally:
            if should_close:
                conn.close()

    def save_insights(self, insights: SessionInsights, conn: Optional[sqlite3.Connection] = None):
        """Save session insights."""
        should_close = False
        if conn is None:
            conn = self._get_connection()
            should_close = True
        
        try:
            for insight in insights.insights:
                conn.execute("""
                    INSERT INTO session_insights (
                        session_id, category, content, importance, primary_theme, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    insights.session_id, insight.category, insight.content,
                    insight.importance, insight.primary_theme, insight.confidence
                ))
            if should_close:
                conn.commit()
        finally:
            if should_close:
                conn.close()

    def save_correlation(self, correlation: CorrelationResult):
        """Save a correlation result and its linked sessions."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO correlations (
                    id, start_date, end_date, narrative, workstreams, next_actions,
                    one_thing, one_thing_reasoning
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                correlation.id,
                correlation.start_date.isoformat(),
                correlation.end_date.isoformat(),
                correlation.narrative,
                json.dumps(correlation.workstreams),
                json.dumps(correlation.next_actions),
                correlation.one_thing,
                correlation.one_thing_reasoning
            ))

            for session_id in correlation.session_ids:
                conn.execute("""
                    INSERT OR IGNORE INTO correlation_sessions (correlation_id, session_id)
                    VALUES (?, ?)
                """, (correlation.id, session_id))
            conn.commit()

    def get_sessions(self, limit: int = 50, platform: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of sessions."""
        query = "SELECT * FROM sessions"
        params = []
        if platform:
            query += " WHERE platform = ?"
            params.append(platform)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a single session with its messages."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            session = dict(row)
            cursor = conn.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp", (session_id,))
            session['messages'] = [dict(r) for r in cursor.fetchall()]
            return session

    def search_sessions(self, query: str) -> List[Dict[str, Any]]:
        """Simple keyword search across sessions and messages."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT DISTINCT s.* FROM sessions s
                JOIN messages m ON s.id = m.session_id
                WHERE s.summary LIKE ? OR s.generated_title LIKE ? OR m.content LIKE ?
                ORDER BY s.started_at DESC
            """, (f"%{query}%", f"%{query}%", f"%{query}%"))
            return [dict(row) for row in cursor.fetchall()]
