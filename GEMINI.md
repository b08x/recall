# GEMINI Context: Recall 🧠

Recall is a modern Python application designed for multi-platform session extraction, correlation, and AI-driven analysis. It enables users to reconstruct their development context by gathering data from various AI assistants, Git history, and personal notes.

## Project Overview

- **Purpose**: Unified tool for capturing and correlating activity across multiple AI and developer platforms.
- **Main Technologies**:
  - **Python 3.14+**: Leverages modern Python features.
  - **uv**: Modern Python package and project manager.
  - **Rich**: Powers the terminal user interface (TUI) and dashboard.
  - **Pydantic / Pydantic-Settings**: Handles data modeling and decoupled configuration.
  - **DSPy**: Powers the AI correlation and session analysis modules. Supports OpenRouter, OpenAI, Ollama, and Mistral.
  - **Tenacity**: Provides robust exponential backoff retry logic for API interactions.
  - **SQLite**: Used for session and message persistence, as well as local state discovery for certain providers (Hermes, OpenCode).
  - **ChromaDB**: Vector database for semantic search and retrieval of session chunks.
  - **Ollama**: Provides local embeddings via `embeddinggemma` for the vector store.

## Architecture & Structure

The project follows a standard `src`-layout for modern Python packages:

- `src/recall/`: Core package directory.
  - `core.py`: Main orchestration logic (`MultiSourceCorrelator`).
  - `cli.py`: Command-line interface entry point.
  - `config.py`: Configuration management via `.env.local`.
  - `utils/`: Common utilities including `RateLimiter` and retry decorators.
  - `models.py`: Unified dataclass and Pydantic models for sessions and messages.
  - `tui.py`: Rich-based dashboard and progress visualization.
  - `logging.py`: Centralized debug logging system.
  - `ai/`: DSPy modules, signatures, and contextual chunking logic.
  - `db/`: Persistence layer.
    - `manager.py`: Orchestrates SQL and Vector storage.
    - `sqlite_store.py`: SQLite implementation for relational data.
    - `vector_store.py`: ChromaDB implementation for semantic embeddings.
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
- **Analysis Caching**: Session analysis (topics, files, actions) is cached in SQLite. Subsequent extractions will re-use this data unless the `--overwrite` flag is used.
- **AI Logic**: All LLM interactions should be encapsulated within DSPy modules in `src/recall/ai/`.
- **Validation**: After modifying core logic, verify both standard CLI output and TUI rendering integrity.

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
