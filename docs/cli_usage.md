# CLI Usage Guide

The `recall` CLI provides a powerful interface for extracting, analyzing, searching, and correlating AI development sessions.

## Global Options

- `--tui`: Enables the Rich TUI dashboard for a live, interactive experience. Recommended for long-running extractions or visual correlation.

---

## Commands

### 1. `extract`
Extracts sessions from AI platforms (Gemini, Claude Code, Hermes, etc.) and persists them in the database.

**Flags:**
- `--days <int>`: Number of days to look back for sessions (default: 7).
- `--platforms <csv>`: Comma-separated list of platforms to extract (e.g., `gemini,claude`).
- `--analyze`: Triggers DSPy-driven topic and insight extraction.
- `--overwrite`: Re-analyzes sessions even if they already exist in the database.
- `--enhance-context`: Enriches insights with relevant material from Git and Obsidian.
- `--model <str>`: DSPy model for general topic extraction.
- `--insights-model <str>`: Specific model for deep insight extraction.
- `--output <path>`: Saves the extracted data to a JSON file instead of printing to console.

**Example:**
```bash
uv run recall extract --days 3 --analyze --enhance-context --platforms claude,hermes
```

### 2. `correlate`
Synthesizes a unified timeline by merging AI sessions with local and remote Git activity.

**Flags:**
- `--days <int>`: Timeframe for correlation (default: 7).
- `--github-repo <owner/repo>`: Optional GitHub repository to fetch remote commits and PRs.
- `--enhance-context`: Leverages documentation and git patterns to provide strategic recommendations.
- `--model <str>`: DSPy model for correlation synthesis.
- `--output <path>`: Saves the correlation result to a JSON file.

**Example:**
```bash
uv run recall correlate --days 7 --github-repo syncopated/recall --enhance-context
```

### 3. `search`
Performs semantic search across all saved sessions using ChromaDB.

**Arguments:**
- `query`: The natural language search query.

**Flags:**
- `--limit <int>`: Maximum number of results to display (default: 5).
- `--platform <str>`: Filter results by a specific platform.

**Example:**
```bash
uv run recall search "how did I implement the rate limiter?" --platform gemini
```

### 4. `dlq` (Dead Letter Queue)
Manages sessions that failed to process (e.g., due to API timeouts or parsing errors).

**Flags:**
- `--list`: Displays all items currently in the queue.
- `--retry`: Attempts to re-process all failed sessions.
- `--clear`: Empties the queue.

**Example:**
```bash
uv run recall dlq --retry
```

---

## Quick Start Recipes

### The "Morning Catch-up"
Analyze everything from the last 2 days with full context enhancement in the TUI:
```bash
uv run recall --tui extract --days 2 --analyze --enhance-context
```

### The "Deep Search"
Find specific technical decisions across your entire history:
```bash
uv run recall search "why did we switch to ChromaDB?"
```

### The "Weekly Synthesis"
Generate a narrative of your week's work, including GitHub commits:
```bash
uv run recall correlate --days 7 --github-repo your-org/your-repo --enhance-context
```
