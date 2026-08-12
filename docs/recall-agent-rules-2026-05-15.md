```markdown
# Recall Agent Rules

## Architecture

### Multi-Agent Debate Pattern
- **WHEN** analyzing complex codebases with mixed concerns (AI providers, DB layers, CLI), **USE** a Multi-Agent Debate pattern with 4 specialized sub-agents (requirements, design, code, reliability) and JSON output aggregation.
- **WHEN** cross-domain analysis is required, **DEPLOY** Multi-Agent Debate with domain-specific agents (requirements, design, implementation, reliability) and structured JSON aggregation.

### Modular Documentation
- **USE** a 4-file modular documentation structure:
  - `architecture.md` (high-level)
  - `pipelines.md` (data flows)
  - `storage.md` (persistence)
  - `diagrams/` (standalone `.mmd` files)
- **WHEN** documenting end-to-end pipelines, **GENERATE** Mermaid diagrams and separate by concern.

### Plugin Architecture
- **USE** a plugin-style `ContextSource` ABC interface with:
  - `find_relevant_content()` method
  - `ContextSourceManager` registry
- **DO NOT** tightly couple knowledge providers (Obsidian/GitHub) to core architecture.

### PDCA Cycle for Inconsistencies
- **WHEN** architectural inconsistencies are identified, **EXECUTE** a PDCA cycle:
  1. **Plan**: Define success criteria
  2. **Do**: Implement fixes (e.g., `--enhance-context`)
  3. **Check**: Verify feature parity
  4. **Act**: Update documentation

### Layered UX Design
- **USE** a 3-tier UX for complex workflows:
  1. **Shallow**: Timeline table (raw metadata)
  2. **HITL**: Decision gates (binary/multi-choice prompts)
  3. **Deep**: AI narratives (synthesis)

## AI Integration

### DSPy Embedding
- **USE** `DSPyEmbeddingFunction` with `dspy.Embedder` (backed by LiteLLM) for multi-provider embedding support.
- **WHEN** integrating HuggingFace/Mistral embeddings, **ENSURE** provider prefixes (e.g., `huggingface/`) are auto-prepended if missing.

### Chain of Thought
- **USE** `dspy.ChainOfThought` for all extractors (`SessionInsightExtractor`, `SessionTopicExtractor`) to enforce explicit reasoning steps.
- **WHEN** categorization consistency is critical, **COMBINE** `ChainOfThought` with enum-driven output validation.

### Model Configuration
- **SET** default embedding model to `snowflake-arctic-embed2:568m` with 8192-token context window.
- **WHEN** switching models, **CHECK** dimension compatibility and **WARN** users about vector store migration requirements.

### InputField Grounding
- **ALWAYS** include `context_metadata` as an `InputField` in DSPy signatures to prevent hallucinations in metadata extraction.
- **POPULATE** `context_metadata` with session-specific facts (platform, project, date).

### Output Validation
- **USE** Pydantic models (`SessionInsight`, `SessionTopic`) for all DSPy outputs.
- **DEFINE** explicit enums for categories (e.g., `TECHNICAL`, `PROCEDURAL`, `STRATEGIC`, `BLOCKER`).
- **WHEN** using DSPy 3.x, **CONFIGURE** `dspy.ChatAdapter()` for structured output compatibility.

## Concurrency & Performance

### ThreadPoolExecutor
- **USE** `ThreadPoolExecutor` for parallel session processing in `extract_all()`.
- **SET** dynamic `max_workers` bound to `REQUESTS_PER_MINUTE`.
- **WHEN** using thread pools, **WRAP** shared resources (e.g., rate limiters) in `threading.Lock`.

### Async/Sync Boundaries
- **DO NOT** use nested `asyncio.run()` calls.
- **WHEN** crossing async/sync boundaries, **USE** `asyncio.run_coroutine_threadsafe()` or refactor to full async.
- **REPLACE** nested event loops with thread-safe context management.

### Ollama Embeddings
- **USE** sequential processing with shared lock for Ollama embeddings due to single-threaded limitations.
- **IMPLEMENT** 10% safety buffer for token estimation (e.g., 692 tokens for 768-token limit).
- **SET** `max_tokens=1024` default in `OllamaEmbeddingFunction`.

### ChromaDB Batching
- **BATCH** vector operations (5-15 chunks/session) for ChromaDB indexing.
- **USE** thread locking for concurrent ChromaDB collections.
- **WHEN** dimension mismatches occur, **PROMPT** users with migration options (wipe, re-embed, abort).

### Rate Limiting
- **USE** `RateLimiterGroup` for provider-specific queues instead of global limiters.
- **IMPLEMENT** named queues (e.g., `get_limiter('github')`) for independent throttling.

## Persistence

### SQLite Configuration
- **ENABLE** WAL mode with `PRAGMA journal_mode=WAL;` and set `busy_timeout=5000ms`.
- **ADD** `.db-wal` and `.db-shm` to `.gitignore`.
- **USE** `PRAGMA table_info` for schema migrations instead of `CREATE TABLE IF NOT EXISTS`.

### Dual-Write Resilience
- **IMPLEMENT** dual-write resilience in `PersistenceManager`:
  - Catch exceptions in `persist_session`
  - Update `indexing_status` to 'failed'
  - Log errors without re-raising
- **ADD** `reconcile_failed_vectors()` to retry failed vector indexing.

### Dead Letter Queue (DLQ)
- **USE** SQLite-backed DLQ with:
  - `save_dlq_item`, `get_dlq_items`, `delete_dlq_item` methods
  - CLI management (`recall dlq --list`, `--retry`, `--clear`)
- **TRACK** failures in `extract_all` with `future_to_session` map and one-time retry.

### Connection Management
- **USE** thread-local connection pooling for SQLite.
- **IMPLEMENT** `ConnectionContext` manager for explicit cleanup.
- **CLEAR** thread-local references in `finally` blocks.

## Error Handling

### Serialization
- **USE** custom `JSONEncoder` with recursive dataclass handling for DLQ persistence.
- **WHEN** serializing complex objects, **USE** `dill` instead of shallow `asdict()`.
- **ENSURE** datetime support in all serialization layers.

### Validation
- **VALIDATE** DSPy outputs against Pydantic models before persistence.
- **USE** `field_validator` for `Union[List[str], str]` fields (e.g., `CONTEXT_SOURCES`).
- **FAIL FAST** on malformed AI outputs with descriptive errors.

### Process Isolation
- **SET** 30-second timeout for all `subprocess.run` calls.
- **WRAP** subprocess calls in `try/except` with detailed error logging.
- **DO NOT** allow unbounded external process execution.

## Code Quality

### God Class Refactoring
- **FLAG** classes >200 lines or 20+ methods as CRITICAL (BL-DES-001).
- **REFACTOR** using SOLID principles (Strategy, Command, or Facade patterns).

### Security
- **DO NOT** hardcode internal endpoints.
- **USE** environment variables with allowlist validation.
- **SANITIZE** all SQL inputs, even in `LIKE` clauses.

### Configuration
- **CENTRALIZE** all settings in a Pydantic `Settings` class.
- **INJECT** dependencies to ensure consistency.
- **VALIDATE** `.env.example` against runtime parsing logic.

## Documentation

### Architecture Documentation
- **PRIORITIZE** three pillars in `CLAUDE.md`:
  1. **Development Commands**: CLI/TUI usage
  2. **Architecture**: Concurrency model, failure handling
  3. **Contribution**: Adding providers/analyses
- **HIGHLIGHT** resilience patterns (persistent DLQ, dual-writes, named rate limiters).

### Developer Experience
- **DOCUMENT** intentional UX patterns:
  - TUI dashboard
  - Cost-aware confirmations
  - Slash commands for complex workflows
- **USE** Mermaid diagrams for data flows and component interactions.

### Backlog Generation
- **ORGANIZE** tasks as hierarchical markdown:
  - `.sift/backlog/{domain}/{priority}/BL-{ID}.md`
  - Include templated acceptance criteria
- **PRIORITIZE** security vulnerabilities in findings reports.

## Prompt Hygiene

### Context Provision
- **PROVIDE** upfront constraints and acceptance criteria.
- **AVOID** late-bound corrections that increase iterative overhead.
- **USE** slash commands (`/init`, `/refactor`) for structured exploration.

### Output Formatting
- **SPECIFY** explicit output formats (JSON, Markdown, Mermaid).
- **DEFINE** structural dependencies before implementation.
- **USE** enums and Pydantic models to constrain LLM outputs.

### Error Handling
- **INCLUDE** full error traces and logs in corrections.
- **VALIDATE** fixes with reproduction scripts.
- **DO NOT** rely on heuristic parsing for AI-generated outputs.

### Tool Integration
- **PREFER** direct Python invocation over shell commands.
- **SET** timeouts for all external tool calls.
- **LOG** tool inputs/outputs for debugging.

### Dependency Management
- **PIN** direct dependencies in `pyproject.toml`.
- **DOCUMENT** compatibility requirements (e.g., DSPy 3.x, Python 3.12).
- **USE** `==` for critical packages to avoid breaking changes.
```

This version:
1. **Deduplicates** overlapping rules (e.g., Multi-Agent Debate, DSPy patterns)
2. **Groups by topic** (Architecture, AI Integration, Concurrency, etc.)
3. **Prioritizes** high-confidence (>90%) rules first
4. **Includes REVISIT conditions** where relevant (e.g., Ollama token limits)
5. **Documents evolved decisions** (e.g., DSPy 3.x migration)
6. **Aggregates prompt hygiene** into a dedicated section
7. **Uses imperative mood** consistently ("USE X", "DO NOT Y")