from typing import List, Dict, Optional, Any
from datetime import datetime
from recall.models import ParsedSession, SessionAnalysis, SessionInsights, CorrelationResult
from recall.db.sqlite_store import SQLiteStore
from recall.db.vector_store import VectorStore
from recall.ai.chunking import ContextualChunker
from recall.logging import debug, error

class PersistenceManager:
    """Orchestrates data flow between SQLite and Vector storage."""

    def __init__(self, 
                 db_path: str = "recall.db", 
                 vector_dir: str = "./chroma_db",
                 ollama_host: str = "http://tinybot:11434"):
        
        self.sqlite = SQLiteStore(db_path)
        self.vector = VectorStore(persist_directory=vector_dir, ollama_host=ollama_host)
        self.chunker = ContextualChunker()

    def persist_session(self, 
                       session: ParsedSession, 
                       analysis: Optional[SessionAnalysis] = None, 
                       insights: Optional[SessionInsights] = None,
                       overwrite: bool = False):
        """Save a session, its analysis, and index its chunks for semantic search."""
        
        # Use a single connection for the relational part of the transaction
        conn = self.sqlite._get_connection()
        try:
            # 1. Relational storage (partial transaction)
            # This saves the session with indexing_status='pending'
            self.sqlite.save_session(session, conn=conn)
            if analysis:
                self.sqlite.save_analysis(analysis, conn=conn)
            if insights:
                self.sqlite.save_insights(insights, conn=conn)
            
            # Commit the relational data first so we don't lose it if vector fails,
            # but it stays marked as 'pending'.
            conn.commit()
            
            # 2. Vector storage
            if overwrite:
                debug(f"Overwrite: deleting existing vector chunks for {session.id}")
                self.vector.delete_session(session.id)
            elif self.vector.has_session(session.id):
                debug(f"Session {session.id} already indexed in vector store, skipping.")
                self.sqlite.update_indexing_status(session.id, 'completed')
                return

            debug(f"Generating chunks and embeddings for session {session.id}...")
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
                
                try:
                    self.vector.add_chunks(session.id, chunks, metadata)
                    # If vector succeeds, mark as completed
                    self.sqlite.update_indexing_status(session.id, 'completed')
                    debug(f"Successfully persisted and indexed session {session.id}")
                except Exception as ve:
                    # If vector fails, mark as failed for reconciliation
                    # We do NOT raise here to ensure Dual-Write resilience:
                    # the SQLite data is already committed.
                    self.sqlite.update_indexing_status(session.id, 'failed')
                    error(f"Vector indexing failed for session {session.id}: {ve}")
        except Exception as e:
            # Only rollback if the initial relational save failed
            try:
                conn.rollback()
            except:
                pass
            raise
        finally:
            conn.close()

    def persist_correlation(self, result: CorrelationResult):
        """Save synthesized correlation data."""
        self.sqlite.save_correlation(result)

    def get_analysis(self, session_id: str) -> Optional[SessionAnalysis]:
        """Retrieve saved analysis for a session from relational store."""
        return self.sqlite.get_analysis(session_id)

    def get_insights(self, session_id: str) -> Optional[SessionInsights]:
        """Retrieve saved insights for a session from relational store."""
        return self.sqlite.get_insights(session_id)

    def semantic_search(self, query: str, platform: Optional[str] = None) -> Dict[str, Any]:
        """Hybrid search: Find relevant chunks and return their session context."""
        where = {"platform": platform} if platform else None
        vector_results = self.vector.query(query, n_results=5, where=where)
        
        # We could enrich these results here by fetching the full session 
        # metadata from SQLite using the session_id in vector_results['metadatas']
        return vector_results
