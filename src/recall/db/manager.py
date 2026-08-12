from typing import List, Dict, Optional, Any, Callable
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
                 embedding_provider: str = "ollama",
                 embedding_model: str = "snowflake-arctic-embed2:568m",
                 ollama_host: str = "http://tinybot:11434",
                 embedding_api_key: Optional[Any] = None,
                 embedding_max_tokens: int = 8192,
                 chunk_max_chars: int = 6000):
        
        self.sqlite = SQLiteStore(db_path)
        self.vector = VectorStore(
            persist_directory=vector_dir, 
            provider=embedding_provider,
            model=embedding_model,
            ollama_host=ollama_host,
            api_key=embedding_api_key,
            max_tokens=embedding_max_tokens
        )
        self.chunker = ContextualChunker(max_chunk_chars=chunk_max_chars)

    def persist_session(self, 
                       session: ParsedSession, 
                       analysis: Optional[SessionAnalysis] = None, 
                       insights: Optional[SessionInsights] = None,
                       overwrite: bool = False,
                       callback: Optional[Callable] = None):
        """Save a session, its analysis, and index its chunks for semantic search."""
        
        # Use a single connection for the relational part of the transaction
        conn = self.sqlite._get_connection()
        try:
            # 1. Relational storage (partial transaction)
            # This saves the session with indexing_status='pending'
            if callback:
                callback(f"Saving relational data for {session.id}...", progress=None)
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
            if callback:
                callback(f"Chunking session {session.id}...", progress=None)
            chunks = self.chunker.chunk_session(session)
            if chunks:
                if callback:
                    callback(f"Embedding {len(chunks)} chunks for {session.id}...", progress=None)
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
                    if callback:
                        callback(f"Indexed session {session.id}.", progress=None)
                except Exception as ve:
                    # If vector fails, mark as failed for reconciliation
                    # We do NOT raise here to ensure Dual-Write resilience:
                    # the SQLite data is already committed.
                    self.sqlite.update_indexing_status(session.id, 'failed')
                    error(f"Vector indexing failed for session {session.id}: {ve}")
                    if callback:
                        callback(f"Indexing failed for {session.id}: {ve}", progress=None)
        except Exception as e:
            # Only rollback if the initial relational save failed
            try:
                conn.rollback()
            except:
                pass
            raise
        finally:
            # We don't close the connection here to allow reuse across 
            # the same thread in the Pool. It is closed when the thread is destroyed.
            pass

    def save_dlq_item(self, session_id: str, payload: Dict[str, Any], error_msg: str):
        """Forward DLQ save to SQLite store."""
        self.sqlite.save_dlq_item(session_id, payload, error_msg)

    def get_dlq_items(self) -> List[Dict[str, Any]]:
        """Retrieve all items from DLQ."""
        return self.sqlite.get_dlq_items()

    def delete_dlq_item(self, dlq_id: int):
        """Forward DLQ delete to SQLite store."""
        self.sqlite.delete_dlq_item(dlq_id)

    def increment_dlq_retry(self, dlq_id: int):
        """Forward DLQ retry increment to SQLite store."""
        self.sqlite.increment_dlq_retry(dlq_id)

    def persist_correlation(self, result: CorrelationResult):
        """Save synthesized correlation data."""
        self.sqlite.save_correlation(result)

    def get_analysis(self, session_id: str) -> Optional[SessionAnalysis]:
        """Retrieve saved analysis for a session from relational store."""
        return self.sqlite.get_analysis(session_id)

    def get_insights(self, session_id: str) -> Optional[SessionInsights]:
        """Retrieve saved insights for a session from relational store."""
        return self.sqlite.get_insights(session_id)

    def reconcile_failed_vectors(self, max_workers: int = 5, callback: Optional[Callable] = None):
        """Find sessions that failed to index and retry them."""
        failed_ids = self.sqlite.get_failed_indexing_sessions()
        if not failed_ids:
            if callback:
                callback("No sessions require reconciliation.", progress=1.0)
            return

        total = len(failed_ids)
        debug(f"Starting reconciliation for {total} sessions with failed indexing status")
        
        processed = 0
        def _reconcile_session(session_id: str):
            nonlocal processed
            try:
                session = self.sqlite.get_parsed_session(session_id)
                if not session:
                    debug(f"Session {session_id} not found during reconciliation, skipping")
                    return
                
                if callback:
                    callback(f"Re-indexing session {session_id}...", progress=processed / total)
                
                analysis = self.sqlite.get_analysis(session_id)
                # Re-run the persistence logic specifically for vector indexing
                # Using overwrite=True ensures we clean up any partial state in Chroma
                self.persist_session(session, analysis, overwrite=True)
                processed += 1
                debug(f"Successfully reconciled session {session_id} ({processed}/{total})")
                
                if callback:
                    callback(f"Re-indexed {processed}/{total} sessions...", progress=processed / total)
            except Exception as e:
                error(f"Reconciliation failed for session {session_id}: {e}")

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            executor.map(_reconcile_session, failed_ids)
            
        if callback:
            callback(f"Re-indexing complete. Processed {processed} sessions.", progress=1.0)

    def semantic_search(self, query: str, platform: Optional[str] = None) -> Dict[str, Any]:
        """Hybrid search: Find relevant chunks and return their session context."""
        where = {"platform": platform} if platform else None
        vector_results = self.vector.query(query, n_results=5, where=where)
        
        # We could enrich these results here by fetching the full session 
        # metadata from SQLite using the session_id in vector_results['metadatas']
        return vector_results

    def check_dimension_compatibility(self) -> tuple[bool, Optional[int], Optional[int]]:
        """
        Check if the current model's dimensions match the existing database.
        Returns (is_compatible, existing_dim, model_dim)
        """
        existing_dim = self.vector.get_dimension()
        if existing_dim is None:
            # Collection is empty or doesn't exist, no compatibility issue
            return True, None, None
            
        model_dim = self.vector.get_model_dimension()
        if model_dim is None:
            # Could not determine model dimension, assume incompatible for safety
            return False, existing_dim, None
            
        return existing_dim == model_dim, existing_dim, model_dim

    def handle_migration(self, option: str):
        """Execute a migration strategy: 'wipe' or 're-embed'."""
        if option == "wipe":
            self.vector.wipe()
            # We don't necessarily reset SQLite status because 'wipe' 
            # might mean starting from scratch for future sessions only.
            # But usually, if we wipe vector, we want to re-index.
            # However, for simplicity 'wipe' here just clears the vector store.
        
        elif option == "re-embed":
            self.vector.wipe()
            # Re-init vector store by re-creating the collection (lazy handled by Chromadb)
            # but we need to reset SQLite so reconcile picks them up
            self.sqlite.reset_all_indexing_status()
            # We don't run reconciliation here, as it might be a long process.
            # The CLI will call it if needed or it will run on next initialization.
