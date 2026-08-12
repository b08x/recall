# Database Layer

**Location**: `src/recall/db/`
**Confidence**: EXTRACTED

## Transformation Contract

The database layer **transforms** parsed session objects, analysis results, and insights **into** persisted relational records in SQLite **and** semantic vector embeddings in ChromaDB **through** dual-write persistence with automatic indexing status tracking **when** vector embeddings are configured; supports DLQ for failed items and dimension compatibility checking.

> The database layer works like a dual-entry bookkeeper — it **maintains both a ledger (SQLite) and a search index (ChromaDB)** so that session data can be both queried precisely and retrieved semantically, **while** the DLQ acts as the reconciliation desk that catches any transactions that failed to post.

## Responsibilities

- Persist sessions, messages, tool calls, and tool results in SQLite
- Index session chunks for semantic search via ChromaDB
- Manage dead-letter queue for failed extraction/indexing operations
- Reconcile failed vector indexes on startup
- Provide hybrid search (semantic + metadata filtering)
- Check embedding dimension compatibility between model changes
- Support database migrations (wipe/re-embed strategies)

## Key Components

| Component | Type | Transformation / Role | Confidence |
|-----------|------|-----------------------|------------|
| `SQLiteStore` | class | **persists** sessions, messages, analysis, insights **into** SQLite with WAL mode | EXTRACTED |
| `VectorStore` | class | **stores** and **queries** semantic embeddings via ChromaDB | EXTRACTED |
| `PersistenceManager` | class | **orchestrates** dual-write between SQLite and VectorStore with chunking | EXTRACTED |
| `DSPyEmbeddingFunction` | class | **embeds** text **via** DSPy (OpenAI, Mistral, HuggingFace, Ollama) | EXTRACTED |
| `OllamaEmbeddingFunction` | class | **embeds** text **via** local Ollama models with safety truncation | EXTRACTED |
| `dlq` table | schema | **captures** failed extraction payloads for retry | EXTRACTED |
| `sessions` table | schema | **stores** parsed session metadata and indexing status | EXTRACTED |
| `messages` table | schema | **stores** individual message content with tool call/result data | EXTRACTED |
| `correlations` table | schema | **stores** synthesized cross-platform correlation results | EXTRACTED |

## Dependencies

**Requires**:
- `sqlite3` — Python's built-in SQLite support
- `chromadb` — Vector database for semantic search
- `httpx` — HTTP client for Ollama embedding service
- `tiktoken` (optional) — Token counting for cost estimation

**Enables**:
- `Core Pipeline` (`MultiSourceCorrelator`) — provides `PersistManager` for all persistence operations
- `AI Modules` — receives vector embeddings for semantic search
- `CLI` — exposes DLQ management and dimension compatibility checks

## Interactions

```mermaid
flowchart TD
    MSC["MultiSourceCorrelator"] -->|persist_session()| PM["PersistenceManager"]
    PM -->|save_session()| SS["SQLiteStore"]
    PM -->|add_chunks()| VS["VectorStore"]
    SS -->|WAL mode| SQLITE[(SQLite)]
    VS -->|semantic search| CHROMA[(ChromaDB)]
    PM -->|DLQ| DLQ["Dead Letter Queue"]
    PM -->|reconciliation| SS
```

## What Users / Developers Experience

- **First encounter**: Developers **typically interact with** `PersistenceManager` as the entry point for all persistence operations
- **After regular use**: The `check_dimension_compatibility()` method **prevents** embedding model mismatches that would corrupt the vector index
- **Failure handling**: Failed vector indexing is caught and recorded in the DLQ; SQLite data is committed first (dual-write resilience)
- **Migration**: `handle_migration()` provides `"wipe"` and `"re-embed"` strategies for changing embedding models

## Known Limitations

**Works well when**: SQLite WAL mode is enabled for concurrent writes; embedding dimensions remain stable between model updates
**May struggle with**: Very large datasets (100k+ sessions) where SQLite may become a bottleneck; ChromaDB memory constraints with large collections
**Requires workarounds for**: ChromaDB collection initialization race conditions; thread-local connection management in long-running processes

## Code Snippets

### Persisting a session
```python
from recall.db import PersistenceManager
from recall.models import ParsedSession, SessionAnalysis, SessionInsights

pm = PersistenceManager(db_path="recall.db", vector_dir="./chroma_db")
pm.persist_session(
    session=session,
    analysis=analysis,
    insights=insights,
    overwrite=False,
    callback=lambda msg, progress: print(msg)
)
```

### Semantic search
```python
results = pm.semantic_search(query="debugging authentication", platform="gemini")
# Returns vector results with metadata
```

## Ruby Pragmatist Insight

The database layer works like a dual-entry accounting system — it **commits to the ledger (SQLite) before posting to the search index (ChromaDB)**, ensuring data integrity even if the vector index fails, **while** the DLQ catches any reconciliation items that didn't post, much like how a bank's nightly batch process catches failed transactions for manual review.
