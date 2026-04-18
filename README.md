# Recall 🧠

Recall is a multi-platform session extraction and correlation tool. It gathers context from various AI assistants (Gemini, Claude, Hermes, OpenCode), local Git history, GitHub, and Obsidian notes to help you reconstruct what you were working on and generate AI-driven summaries of your workstreams.

## Features

- **Parallel Extraction**: High-performance session extraction and analysis using `ThreadPoolExecutor` and provider-specific **named `RateLimiter` queues** to prevent global throttling.
- **Resilient Processing**: Integrated **Dead Letter Queue (DLQ)** with an automatic one-time retry mechanism to capture and handle transient session processing failures.
- **Transactional Dual-Writes**: Atomic synchronization between relational SQLite data and ChromaDB vector chunks with **WAL-enabled concurrency safety** and automatic failed-write reconciliation.
- **Cost Management**: Integrated **Pre-flight Token Estimation** using `tiktoken` with user confirmation thresholds to prevent API cost overruns.
- **Schema Safety**: Uses **DSPy Pydantic-aware Predictors** and strict models for AI-generated insights, ensuring output consistency and eliminating heuristic parsing.
- **Safety-First Windowing**: Conservative chunking and token-aware context management with **built-in safety buffers** to maximize input quality and prevent local model failures.
- **Auto-Migration**: Self-healing SQLite schema that automatically handles database updates.
- **Robustness**: Built-in conservative rate limiting and exponential backoff retries for all AI and GitHub API interactions.
- **Semantic Search**: Leverage ChromaDB and Ollama (`embeddinggemma`) to find sessions based on meaning, not just keywords.
- **Persistent Data Layer**: Automatic storage of all sessions, messages, and AI-driven analyses in a local SQLite database with full object reconstruction.
- **Git Correlation**: Match AI sessions with local and remote Git commits to see code changes in context.
- **Obsidian Integration**: Include relevant notes from your personal knowledge base.
- **AI Synthesis**: Uses [DSPy](https://github.com/stanfordnlp/dspy) to generate narratives and identify next actions (supports Mistral, OpenAI, Ollama).
- **Rich TUI**: A beautiful dashboard for monitoring extraction and correlation.

## Installation

This project uses `uv` for dependency management.

```bash
# Clone the repository
git clone https://github.com/syncopated/recall
cd recall

# Install dependencies
uv sync
```

*Note: ChromaDB and Ollama are required for semantic search features.*

## Configuration

Copy the example environment file and fill in your API keys and rate limits:

```bash
cp .env.local.example .env.local
# Edit .env.local with your settings (API keys, requests per minute, etc.)
```

## Usage

### TUI Dashboard (Recommended)

Run extraction and correlation with a live dashboard:

```bash
uv run recall --tui extract --days 3 --analyze
uv run recall --tui correlate --days 7 --github-repo owner/repo
```

### CLI Commands

Extract sessions and persist them:
```bash
uv run recall extract --days 7 --platforms gemini,claude --analyze
# Use --insights-model to specify a deeper model for session insights
uv run recall extract --days 3 --analyze --insights-model openai/gpt-4o
# Use --overwrite to re-run AI analysis for previously processed sessions
uv run recall extract --days 7 --analyze --overwrite
```

Semantic search across all saved sessions:
```bash
uv run recall search "how did I fix that typescript error?"
```

Correlate and print summary:
```bash
uv run recall correlate --days 14
```

## Project Structure

- `src/recall/core.py`: The main orchestration engine.
- `src/recall/db/`: Persistence layer (SQLite + ChromaDB).
- `src/recall/tui.py`: Rich-based TUI implementation.
- `src/recall/config.py`: Pydantic-settings configuration.
- `src/recall/providers/`: Specialized extractors for different platforms.
- `src/recall/ai/`: DSPy modules and signatures for analysis.

## License

MIT
