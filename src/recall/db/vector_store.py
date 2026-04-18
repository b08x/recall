import httpx
import json
import uuid
import time
from typing import List, Dict, Optional, Any
from recall.logging import debug, error
from recall.utils.limiter import get_default_limiter, get_retry_decorator

try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False

try:
    import chromadb
    from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    # Mock classes for type hinting if chromadb is missing
    class EmbeddingFunction: pass
    class Documents: pass
    class Embeddings: pass

class OllamaEmbeddingFunction(EmbeddingFunction):
    """Custom embedding function for Ollama's embeddinggemma model."""
    
    def __init__(self, host: str = "http://tinybot:11434", model: str = "embeddinggemma", max_tokens: int = 2048):
        self.host = host
        self.model = model
        self.max_tokens = max_tokens
        self.client = httpx.Client(timeout=60.0)  # Increased timeout
        self.limiter = get_default_limiter()
        self.encoding = tiktoken.get_encoding("cl100k_base") if HAS_TIKTOKEN else None

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = []
        
        # Configure retry based on global limiter settings (or defaults)
        retry_decorator = get_retry_decorator(
            max_attempts=3,
            min_wait=1.0,
            max_wait=10.0,
            exceptions=(httpx.HTTPError, Exception)
        )

        @retry_decorator
        def _get_embedding(text: str):
            self.limiter.wait()
            response = self.client.post(
                f"{self.host}/api/embeddings",
                json={"model": self.model, "prompt": text}
            )
            response.raise_for_status()
            return response.json()["embedding"]

        for text in input:
            # Use proper tokenizer to safely maximize context window without triggering 500 errors
            if self.encoding:
                tokens = self.encoding.encode(text)
                if len(tokens) > self.max_tokens:
                    safe_text = self.encoding.decode(tokens[:self.max_tokens])
                else:
                    safe_text = text
            else:
                # Fallback to naive truncation if tiktoken is missing
                safe_text = text[:3000] if len(text) > 3000 else text
            
            embedding = _get_embedding(safe_text)
            embeddings.append(embedding)
                
        return embeddings

    def name(self) -> str:
        return f"ollama_{self.model}"

class VectorStore:
    """Handles semantic storage and retrieval of session chunks using ChromaDB."""

    def __init__(self, 
                 collection_name: str = "recall_sessions", 
                 persist_directory: str = "./chroma_db",
                 ollama_host: str = "http://tinybot:11434",
                 ollama_model: str = "embeddinggemma"):
        
        if not CHROMA_AVAILABLE:
            debug("ChromaDB not available. Semantic features will be disabled.")
            self.collection = None
            return

        self.client = chromadb.PersistentClient(path=persist_directory)
        self.embedding_fn = OllamaEmbeddingFunction(host=ollama_host, model=ollama_model)
        
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"}
        )

    def add_chunks(self, 
                   session_id: str, 
                   chunks: List[str], 
                   metadata: Optional[List[Dict[str, Any]]] = None):
        """Add session text chunks to the vector database."""
        if not self.collection:
            return

        ids = [f"{session_id}_{i}_{uuid.uuid4().hex[:8]}" for i in range(len(chunks))]
        
        # Ensure metadata includes session_id
        if not metadata:
            metadata = [{"session_id": session_id} for _ in range(len(chunks))]
        else:
            for m in metadata:
                m["session_id"] = session_id

        self.collection.add(
            documents=chunks,
            metadatas=metadata,
            ids=ids
        )
        debug(f"Added {len(chunks)} chunks to vector store for session {session_id}")

    def delete_session(self, session_id: str):
        """Delete all chunks associated with a session."""
        if not self.collection:
            return
        
        try:
            self.collection.delete(where={"session_id": session_id})
            debug(f"Deleted existing chunks for session {session_id}")
        except Exception as e:
            error(f"Error deleting chunks for session {session_id}: {e}")

    def has_session(self, session_id: str) -> bool:
        """Check if a session already has chunks in the vector store."""
        if not self.collection:
            return False
            
        try:
            result = self.collection.get(where={"session_id": session_id}, limit=1)
            return len(result.get("ids", [])) > 0
        except Exception as e:
            debug(f"Error checking session {session_id} in vector store: {e}")
            return False

    def query(self, query_text: str, n_results: int = 5, where: Optional[Dict] = None):
        """Find the most semantically relevant chunks."""
        if not self.collection:
            return []

        return self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where
        )
