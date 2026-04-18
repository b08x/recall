# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview
Recall is a multi-platform session extraction and correlation tool that gathers context from AI assistants (Gemini, Claude, Hermes, OpenCode), Git history, GitHub, and Obsidian notes. It uses Python 3.12+, DSPy for AI analysis, SQLite with WAL mode for persistence, and ChromaDB for vector storage. Features intelligent context enhancement through a pluggable ContextSource architecture that enriches session insights with relevant documentation and development patterns.

## Development Commands

### Setup and Environment
```bash
# Install dependencies
uv sync

# Setup configuration
cp .env.local.example .env.local
# Edit .env.local with API keys and settings
```

### Running the Application
```bash
# Standard CLI extraction with analysis and context enhancement
uv run recall extract --days 3 --analyze --enhance-context

# TUI dashboard (recommended for development)
uv run recall --tui extract --days 3 --analyze --enhance-context

# Semantic search
uv run recall search "authentication"

# Enhanced correlation with GitHub and context sources
uv run recall --tui correlate --days 7 --github-repo owner/repo --enhance-context

# DLQ management (for failed sessions)
uv run recall dlq --list
uv run recall dlq --retry
uv run recall dlq --clear
```

### Development Utilities
```bash
# Update knowledge graph after code changes
graphify update .

# Check project structure
codemap .
codemap --diff  # See changes vs main branch
```

## Architecture Overview

### Core Components
- **Core Orchestration** (`core.py`): Main engine with concurrent session analysis via ThreadPoolExecutor, token estimation, and persistent DLQ with 30s timeouts on external subprocess calls
- **CLI Interface** (`cli.py`): Command-line with cost-aware confirmations, DLQ management, and context enhancement options
- **Configuration** (`config.py`): Pydantic-settings via `.env.local` supporting MAX_WORKERS, context enhancement settings, and safety limits
- **TUI Dashboard** (`tui.py`): Rich-based terminal interface with context enhancement support
- **Persistence Layer** (`db/`): Atomic dual-writes between SQLite (WAL mode) and ChromaDB with thread-local connection pooling
- **AI Analysis** (`ai/`): DSPy modules with Pydantic-aware predictors for schema safety and context enhancement
- **Providers** (`providers/`): Platform-specific extractors for Gemini, Claude Code, Hermes, etc.
- **Context Sources** (`context.py`, `providers/context/`): Pluggable architecture for enriching insights with Obsidian documentation and Git development patterns

### Key Design Patterns
- **Transactional Dual-Writes**: Atomic synchronization between relational and vector storage with automatic failed-write reconciliation
- **Named Rate Limiting**: Provider-specific throttling via named queues (e.g., `gemini`, `github`, `embeddings`) to prevent global stalls
- **Robust Session Parsing**: Standardized **filtering of empty messages** across all providers. Special handling for Claude Code to extract **tool results**, **thinking blocks**, and resolve complex **project paths for subagents**.
- **Persistent DLQ**: Survives application restarts, allows retry of failed sessions
- **Safety-First Processing**: Conservative chunking, token-aware context management with built-in safety buffers
- **Schema Safety**: DSPy Pydantic-aware predictors eliminate heuristic parsing

### Data Flow
1. **Extraction**: Platform providers gather sessions using named rate limiters
2. **Chunking**: `ContextualChunker` splits large sessions for token limits
3. **Analysis**: DSPy modules extract topics, insights using structured Pydantic outputs
4. **Context Enhancement** (Optional): ContextSource plugins enrich insights with relevant documentation and Git patterns using hybrid relevance matching
5. **Persistence**: Atomic writes to SQLite + ChromaDB with DLQ for failures
6. **Reconciliation**: Auto-healing of failed vector writes on startup

## Development Guidelines

### Adding New Analysis Types
To add a session analysis metric (e.g., complexity, sentiment):

1. **Update Signature**: Add output field to `SessionTopicExtractor` (src/recall/ai/signatures.py)
2. **Update Module**: Modify `SessionAnalysisModule.forward` (src/recall/ai/modules.py) for aggregation
3. **Update Models**: Add field to `SessionAnalysis` Pydantic model (src/recall/models.py)
4. **Update Persistence**: Modify sqlite_store.py schema and save/get methods
5. **Update Orchestrator**: Ensure core.py maps results to SessionAnalysis object
6. **Verification**: Test DSPy signatures, aggregation logic, schema migration, TUI display

### Adding New Providers
1. Create provider class in `src/recall/providers/` inheriting from base provider
2. Implement required methods: `extract_sessions()`, `get_session_content()`
3. Add provider to factory in `__init__.py`
4. Update configuration for any required API keys or settings
5. Add named rate limiter in utils/limiter.py if needed

### Adding New Context Sources
To add a context source for insight enhancement (e.g., Slack, Linear, Jira):

1. **Create Context Source**: Create class in `src/recall/providers/context/` inheriting from `ContextSource`
2. **Implement Interface**: Implement `find_relevant_content()` and `is_available()` methods
3. **Hybrid Matching**: Implement relevance scoring using semantic, keyword, temporal, and file-path matching
4. **Register Source**: Add to context manager factory in `recall.context.create_context_manager()`
5. **Configuration**: Add source name to `context_sources` config list and any required settings
6. **Testing**: Verify relevance scoring and context integration with enhanced insights

### Code Conventions
- Use `uv` for all dependency management and execution
- Follow absolute imports within the `recall` namespace
- Use centralized logging via `recall.logging` module (debug, info, error)
- Encapsulate all LLM interactions within DSPy modules in `src/recall/ai/`
- Validate TUI rendering after core logic modifications
- Use thread-safe patterns for database operations

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
