# GEMINI Context: Recall 🧠

Recall is a modern Python application designed for multi-platform session extraction, correlation, and AI-driven analysis. It enables users to reconstruct their development context by gathering data from various AI assistants, Git history, and personal notes.

## Project Overview

- **Purpose**: Unified tool for capturing and correlating activity across multiple AI and developer platforms.
- **Main Technologies**:
  - **Python 3.12+**: Compatible with standard environments.
  - **uv**: Modern Python package and project manager.
  - **Rich**: Powers the terminal user interface (TUI) and dashboard.
  - **Pydantic / Pydantic-Settings**: Handles data modeling and decoupled configuration.
  - **DSPy**: Powers the AI correlation and session analysis modules with **Pydantic-enforced predictors**.
  - **Tenacity**: Provides robust exponential backoff retry logic for API interactions.
  - **SQLite**: Relational storage for sessions and insights with **transactional tracking**.
  - **ChromaDB**: Vector database for semantic search.
  - **Ollama / tiktoken**: Local embeddings with **precise token-window management**.

## Architecture & Structure

The project follows a standard `src`-layout for modern Python packages:

- `src/recall/`: Core package directory.
  - `core.py`: Main orchestration logic with **token estimation pre-flight checks**.
  - `cli.py`: Command-line interface with **cost-aware user confirmations**.
  - `config.py`: Configuration management via `.env.local`.
  - `utils/`: Common utilities including `RateLimiter` and retry decorators.
  - `models.py`: Unified dataclass and Pydantic models.
  - `tui.py`: Rich-based dashboard.
  - `logging.py`: Centralized debug logging system.
  - `ai/`: DSPy modules and signatures using **Pydantic-aware predictors** for schema safety.
  - `db/`: Persistence layer with **Atomic Dual-Writes**.
    - `manager.py`: Orchestrates transactional SQL and Vector synchronization.
    - `sqlite_store.py`: SQLite implementation with **auto-migration** and indexing status tracking.
    - `vector_store.py`: ChromaDB implementation with **tiktoken** truncation.
  - `providers/`: Specialized extractors for Gemini, Claude Code, Hermes, OpenCode, Obsidian, and Git.

## Building and Running

### Setup
Ensure `uv` is installed, then synchronize the environment:
```bash
uv sync
```

### Execution
Run the application via the `uv` entrypoint:
```bash
# Standard CLI
uv run recall extract --days 3 --analyze

# Semantic Search
uv run recall search "authentication"

# Rich TUI Dashboard
uv run recall --tui correlate --github-repo owner/repo
```

### Configuration
Manage paths, API keys, and rate limits in `.env.local`. See `.env.local.example` for the available fields including `REQUESTS_PER_MINUTE` and `RETRY_MAX_ATTEMPTS`.

## Development Conventions

- **Environment**: Always use `uv` for dependency management and execution.
- **Code Style**: 
  - Follow modern Python idioms and type hints.
  - Use absolute imports within the `recall` namespace.
- **Logging**: Use the centralized `recall.logging` module (`debug`, `info`, `error`) to ensure logs are captured both in the log file and the TUI dashboard.
- **Analysis Caching**: Session analysis (topics, files, actions) and categorized insights are cached in SQLite. Subsequent extractions will re-use this data unless the `--overwrite` flag is used.
- **Deep Insights**: Beyond basic topic extraction, the system generates categorized insights (Technical, Strategic, Procedural, etc.) using configurable models and providers.
- **AI Logic**: All LLM interactions should be encapsulated within DSPy modules in `src/recall/ai/`.
- **Validation**: After modifying core logic, verify both standard CLI output and TUI rendering integrity.

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
