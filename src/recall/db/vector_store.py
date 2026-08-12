import httpx
import json
import uuid
import time
import threading
from typing import List, Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor
from recall.logging import debug, error
from recall.utils.limiter import get_limiter, get_retry_decorator

try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False

try:
    import dspy
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False

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

class DSPyEmbeddingFunction(EmbeddingFunction):
    """Embedding function using dspy.Embedder to support multiple providers (OpenAI, Mistral, HuggingFace, etc)."""
    
    def __init__(self, model: str, provider: str = "openai", api_key: Optional[str] = None, **kwargs):
        if not DSPY_AVAILABLE:
            raise ImportError("dspy is required for DSPyEmbeddingFunction. Install it with 'uv add dspy-ai'.")
        
        self.provider = provider
        self.model = model
        
        # Map provider to LiteLLM prefix if not already present
        model_string = model
        prefix_map = {
            "openai": "openai/",
            "mistral": "mistral/",
            "huggingface": "huggingface/",
            "ollama": "ollama/"
        }
        
        prefix = prefix_map.get(provider, "")
        if prefix and not model.startswith(prefix):
            # For HuggingFace, we want to allow org/model but still prefix with huggingface/
            # unless it's already there.
            model_string = f"{prefix}{model}"
            
        # Set API key in environment for LiteLLM if provided
        if api_key:
            import os
            from recall.config import SecretStr
            raw_key = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
            
            env_map = {
                "openai": "OPENAI_API_KEY",
                "mistral": "MISTRAL_API_KEY",
                "huggingface": "HUGGINGFACE_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY"
            }
            env_var = env_map.get(provider)
            if env_var:
                os.environ[env_var] = raw_key
                debug(f"Set {env_var} for DSPy embedding provider {provider}")

        self.embedder = dspy.Embedder(model_string, **kwargs)
        self.limiter = get_limiter("embeddings")
        debug(f"Initialized DSPyEmbedder with model: {model_string}")

    def __call__(self, input: Documents) -> Embeddings:
        self.limiter.wait()
        try:
            # dspy.Embedder returns a list of embeddings
            return self.embedder(input)
        except Exception as e:
            error(f"DSPy embedding error: {e}")
            raise

    def name(self) -> str:
        return f"dspy_{self.provider}_{self.model}".replace("/", "_")

class OllamaEmbeddingFunction(EmbeddingFunction):
    """Custom embedding function for Ollama's embedding models with safety truncation."""
    
    _lock = threading.Lock()  # Shared lock across all instances to protect Ollama host

    def __init__(self, host: str = "http://tinybot:11434", model: str = "snowflake-arctic-embed2:568m", max_tokens: int = 8192):
        self.host = host
        self.model = model
        self.max_tokens = max_tokens
        # 10% safety buffer to account for tokenizer differences between cl100k_base and local model
        self.safe_limit = int(max_tokens * 0.9)
        self.client = httpx.Client(timeout=60.0)
        self.limiter = get_limiter("embeddings")
        self.encoding = tiktoken.get_encoding("cl100k_base") if HAS_TIKTOKEN else None

    def __call__(self, input: Documents) -> Embeddings:
        # Use proper tokenizer to safely maximize context window
        safe_inputs = []
        for i, text in enumerate(input):
            if self.encoding:
                tokens = self.encoding.encode(text)
                if len(tokens) > self.safe_limit:
                    debug(f"Truncating chunk {i} from {len(tokens)} to {self.safe_limit} tokens (buffer active)")
                    safe_inputs.append(self.encoding.decode(tokens[:self.safe_limit]))
                else:
                    safe_inputs.append(text)
            else:
                safe_chars = self.safe_limit * 3
                if len(text) > safe_chars:
                    debug(f"Truncating chunk {i} to {safe_chars} characters (tiktoken unavailable)")
                    safe_inputs.append(text[:safe_chars])
                else:
                    safe_inputs.append(text)

        # Configure retry based on global limiter settings (or defaults)
        retry_decorator = get_retry_decorator(
            max_attempts=3,
            min_wait=1.0,
            max_wait=10.0,
            exceptions=(httpx.HTTPError, Exception)
        )

        @retry_decorator
        def _get_embedding(text: str):
            self.limiter.wait() # Wait outside the lock
            with self._lock:  # Ensure only one thread calls Ollama at a time
                char_count = len(text)
                token_count = len(self.encoding.encode(text)) if self.encoding else "unknown"
                debug(f"Requesting embedding for chunk: {char_count} chars, ~{token_count} tokens")
                
                try:
                    response = self.client.post(
                        f"{self.host}/api/embeddings",
                        json={"model": self.model, "prompt": text}
                    )
                    response.raise_for_status()
                    return response.json()["embedding"]
                except httpx.HTTPStatusError as e:
                    error(f"Ollama embedding error ({e.response.status_code}): {e.response.text}")
                    raise

        embeddings = []
        for text in safe_inputs:
            embeddings.append(_get_embedding(text))
                
        return embeddings

    def name(self) -> str:
        return f"ollama_{self.model}"

class VectorStore:
    """Handles semantic storage and retrieval of session chunks using ChromaDB."""

    def __init__(self, 
                 collection_name: str = "recall_sessions", 
                 persist_directory: str = "./chroma_db",
                 provider: str = "ollama",
                 model: str = "snowflake-arctic-embed2:568m",
                 ollama_host: str = "http://tinybot:11434",
                 api_key: Optional[Any] = None,
                 max_tokens: int = 8192):
        
        if not CHROMA_AVAILABLE:
            debug("ChromaDB not available. Semantic features will be disabled.")
            self.collection = None
            return

        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(path=persist_directory)
        
        if provider == "ollama":
            self.embedding_fn = OllamaEmbeddingFunction(
                host=ollama_host, 
                model=model,
                max_tokens=max_tokens
            )
        else:
            self.embedding_fn = DSPyEmbeddingFunction(
                model=model,
                provider=provider,
                api_key=api_key
            )
        
        self.collection = None
        self._ensure_collection()

    def _ensure_collection(self):
        """Ensure the ChromaDB collection is initialized."""
        if self.collection is not None:
            return self.collection
            
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"}
        )
        return self.collection

    def get_dimension(self) -> Optional[int]:
        """Get the dimension of existing embeddings in the collection."""
        collection = self._ensure_collection()
        if not collection:
            return None
        
        try:
            # Fetch one item to check its embedding dimension
            result = collection.get(limit=1, include=["embeddings"])
            if result is not None and result.get("embeddings") is not None and len(result["embeddings"]) > 0:
                return len(result["embeddings"][0])
        except Exception as e:
            debug(f"Could not determine existing dimension: {e}")
        return None

    def get_model_dimension(self) -> Optional[int]:
        """Determine the dimension of the current embedding model."""
        if not self.embedding_fn:
            return None
        
        try:
            # Embed a dummy string to see what dimension it produces
            test_embedding = self.embedding_fn(["test"])
            if test_embedding and len(test_embedding) > 0:
                return len(test_embedding[0])
        except Exception as e:
            error(f"Could not determine model dimension: {e}")
        return None

    def wipe(self):
        """Delete the entire collection."""
        if not self.collection:
            return
        
        try:
            name = self.collection.name
            self.client.delete_collection(name)
            self.collection = None
            debug(f"Wiped collection {name}")
        except Exception as e:
            error(f"Error wiping collection: {e}")

    def add_chunks(self, 
                   session_id: str, 
                   chunks: List[str], 
                   metadata: Optional[List[Dict[str, Any]]] = None):
        """Add session text chunks to the vector database."""
        collection = self._ensure_collection()
        if not collection:
            return

        ids = [f"{session_id}_{i}_{uuid.uuid4().hex[:8]}" for i in range(len(chunks))]
        
        # Ensure metadata includes session_id
        if not metadata:
            metadata = [{"session_id": session_id} for _ in range(len(chunks))]
        else:
            for m in metadata:
                m["session_id"] = session_id

        collection.add(
            documents=chunks,
            metadatas=metadata,
            ids=ids
        )
        debug(f"Added {len(chunks)} chunks to vector store for session {session_id}")

    def delete_session(self, session_id: str):
        """Delete all chunks associated with a session."""
        collection = self._ensure_collection()
        if not collection:
            return
        
        try:
            collection.delete(where={"session_id": session_id})
            debug(f"Deleted existing chunks for session {session_id}")
        except Exception as e:
            error(f"Error deleting chunks for session {session_id}: {e}")

    def has_session(self, session_id: str) -> bool:
        """Check if a session already has chunks in the vector store."""
        collection = self._ensure_collection()
        if not collection:
            return False
            
        try:
            result = collection.get(where={"session_id": session_id}, limit=1)
            return len(result.get("ids", [])) > 0
        except Exception as e:
            debug(f"Error checking session {session_id} in vector store: {e}")
            return False

    def query(self, query_text: str, n_results: int = 5, where: Optional[Dict] = None):
        """Find the most semantically relevant chunks."""
        collection = self._ensure_collection()
        if not collection:
            return []

        return collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where
        )
