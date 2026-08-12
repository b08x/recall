# Data Flow

**Transformation Pipeline**: session data → extraction → normalization → analysis → context enrichment → correlation → persistence → search

## Primary Operation: Session Extraction and Correlation

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Core as MultiSourceCorrelator
    participant Providers as Provider Layer
    participant AI as AI Modules
    participant Context as Context Sources
    participant DB as Database Layer
    participant Storage as Storage

    User->>CLI: `recall extract --days 7 --analyze`
    CLI->>Core: initialize(MultiSourceCorrelator)
    Core->>Providers: extract(date_range)
    
    loop Per Platform
        Providers->>Core: ParsedSession objects
    end
    
    Core->>AI: SessionAnalysisModule.forward(session)
    AI->>AI: ContextualChunker.chunk_session()
    AI->>AI: SessionTopicExtractor (DSPy)
    AI-->>Core: topics, files_touched, key_actions
    
    Core->>AI: SessionInsightModule.forward(session)
    AI->>AI: SessionInsightExtractor (DSPy)
    AI-->>Core: categorized insights
    
    alt Context Enhancement Enabled
        Core->>Context: ContextSourceManager.enhance_insights()
        Context->>Context: GitContextSource.find_relevant_content()
        Context->>Context: ObsidianContextSource.find_relevant_content()
        Context->>Context: QMDContextSource.query()
        Context-->>Core: ContextMatch objects
        Core->>AI: ContextEnhancementModule (DSPy)
        AI-->>Core: enhanced insights
    end
    
    Core->>DB: PersistenceManager.persist_session()
    DB->>DB: SQLiteStore.save_session()
    DB->>DB: VectorStore.add_chunks()
    DB-->>Core: indexing_status
    
    Note over Core: Dual-write complete
    Core-->>CLI: Extraction complete
    
    User->>CLI: `recall correlate --github-repo owner/name`
    CLI->>Core: correlate_with_github()
    Core->>DB: retrieve sessions + commits
    Core->>AI: CorrelationModule.forward()
    AI->>AI: TimelineSynthesizer (DSPy)
    AI->>AI: OneThingGenerator (DSPy)
    AI-->>Core: narrative, workstreams, next_actions
    Core->>DB: PersistenceManager.persist_correlation()
    Core-->>CLI: Timeline generated
```

## Secondary Flows

### Semantic Search

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Core
    participant DB as PersistenceManager
    participant VS as VectorStore

    User->>CLI: `recall search "query"`
    CLI->>Core: semantic_search(query)
    Core->>DB: PersistenceManager.semantic_search()
    DB->>VS: vector.query(embedding)
    VS-->>DB: results with metadata
    DB-->>Core: enriched results
    Core-->>CLI: formatted results
```

### DLQ Retry

```mermaid
sequenceDiagram
    participant User
    participant CLI
    participant Core
    participant DB as PersistenceManager

    User->>CLI: `recall dlq --retry`
    CLI->>Core: retry_failed_items()
    Core->>DB: get_dlq_items()
    loop For each DLQ item
        DB->>Core: session_id, payload, error
        Core->>Providers: extract(session_id)
        alt Success
            Core->>DB: persist_session()
            DB->>DB: delete_dlq_item()
        else Failure
            DB->>DB: increment_dlq_retry()
        end
    end
    Core-->>CLI: Retry results
```

## Transformation Pipeline

1. **[Input Stage]**: Platform-specific session files and APIs **provide** raw session data at user-specified date ranges through provider implementations
2. **[Extraction Stage]**: `BaseProvider.extract()` **converts** platform-specific formats into `ParsedSession` objects with normalized message structures
3. **[Analysis Stage]**: `SessionAnalysisModule` and `SessionInsightModule` **transform** raw sessions **into** topics, key actions, and categorized insights using DSPy
4. **[Enrichment Stage]**: `ContextEnhancementModule` **enhances** base insights **with** contextual matches from Git, Obsidian, and QMD sources (optional)
5. **[Correlation Stage]**: `CorrelationModule` **synthesizes** multi-source data (sessions + commits + file changes) **into** unified timeline and workstream narratives
6. **[Persistence Stage]**: `PersistenceManager` **persists** sessions to SQLite and chunks to ChromaDB via dual-write with indexing status tracking
7. **[Search Stage]**: `semantic_search()` **queries** ChromaDB embeddings with metadata filtering to retrieve relevant session context

## Critical Paths

- **[Extraction Path]**: Provider → ParsedSession → AI Analysis → Persistence — this is the core data path that all features depend on
- **[Search Path]**: Query → Embedding → Vector Search → Metadata Join → Results — enables discovery and retrieval
- **[Correlation Path]**: Sessions + Commits → TimelineSynthesizer → Narrative — the highest-value feature for cross-platform understanding

## Error Handling Data Flow

Failed operations follow a resilience pattern:
1. Provider extraction errors → logged with `error()`, session may be skipped
2. AI analysis errors → logged, insights default to empty
3. Vector indexing failures → recorded in DLQ for retry
4. SQLite commit failures → raises exception (dual-write resilience: vector not written)
5. DLQ reconciliation retries → limited by `retry_max_attempts` setting
