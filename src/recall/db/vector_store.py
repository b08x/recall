import httpx
import json
import uuid
from typing import List, Dict, Optional, Any
from recall.logging import debug, error

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
    
    def __init__(self, host: str = "http://tinybot:11434", model: str = "embeddinggemma"):
        self.host = host
        self.model = model
        self.client = httpx.Client(timeout=30.0)

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = []
        for text in input:
            try:
                # Truncate text to avoid 500 errors from Ollama on overly large inputs
                # 6000 chars is a safe limit for most embedding models
                safe_text = text[:6000] if len(text) > 6000 else text
                
                response = self.client.post(
                    f"{self.host}/api/embeddings",
                    json={"model": self.model, "prompt": safe_text}
                )
                response.raise_for_status()
                data = response.json()
                embeddings.append(data["embedding"])
            except Exception as e:
                error(f"Ollama embedding error: {e}")
                # Return zero vector on error to maintain dimension consistency
                embeddings.append([0.0] * 768)
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

    def query(self, query_text: str, n_results: int = 5, where: Optional[Dict] = None):
        """Find the most semantically relevant chunks."""
        if not self.collection:
            return []

        return self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where
        )
