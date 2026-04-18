from typing import List, Dict, Optional, Any
from datetime import datetime
from recall.models import ParsedSession, SessionAnalysis, CorrelationResult
from recall.db.sqlite_store import SQLiteStore
from recall.db.vector_store import VectorStore
from recall.ai.chunking import ContextualChunker
from recall.logging import debug

class PersistenceManager:
    """Orchestrates data flow between SQLite and Vector storage."""

    def __init__(self, 
                 db_path: str = "recall.db", 
                 vector_dir: str = "./chroma_db",
                 ollama_host: str = "http://tinybot:11434"):
        
        self.sqlite = SQLiteStore(db_path)
        self.vector = VectorStore(persist_directory=vector_dir, ollama_host=ollama_host)
        self.chunker = ContextualChunker()

    def persist_session(self, session: ParsedSession, analysis: Optional[SessionAnalysis] = None):
        """Save a session, its analysis, and index its chunks for semantic search."""
        # 1. Relational storage
        self.sqlite.save_session(session)
        if analysis:
            self.sqlite.save_analysis(analysis)

        # 2. Vector storage
        chunks = self.chunker.chunk_session(session)
        if chunks:
            # Create basic metadata for each chunk
            metadata = []
            for _ in chunks:
                m = {
                    "platform": session.source_tool,
                    "project": session.project_name or "unknown",
                    "timestamp": session.started_at.isoformat() if session.started_at else None
                }
                if analysis:
                    m["topics"] = ", ".join(analysis.topics[:5])
                metadata.append(m)
            
            self.vector.add_chunks(session.id, chunks, metadata)

    def persist_correlation(self, result: CorrelationResult):
        """Save synthesized correlation data."""
        self.sqlite.save_correlation(result)

    def semantic_search(self, query: str, platform: Optional[str] = None) -> Dict[str, Any]:
        """Hybrid search: Find relevant chunks and return their session context."""
        where = {"platform": platform} if platform else None
        vector_results = self.vector.query(query, n_results=5, where=where)
        
        # We could enrich these results here by fetching the full session 
        # metadata from SQLite using the session_id in vector_results['metadatas']
        return vector_results
