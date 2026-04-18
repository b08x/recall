# Design Document: Recall Refactor & TUI Implementation

## Overview
Refactor the `recall` project into a modern `uv` project with decoupled configuration and a `rich`-based TUI.

## 1. Project Structure
Transition to a `src`-layout as recommended for modern Python packages.

```text
recall/
├── pyproject.toml
├── .env.local
├── src/
│   └── recall/
│       ├── __init__.py
│       ├── cli.py (was recall_cli.py)
│       ├── core.py
│       ├── models.py
│       ├── config.py (new)
│       ├── tui.py (new)
│       ├── ai/
│       │   ├── __init__.py
│       │   ├── chunking.py
│       │   ├── modules.py
│       │   └── signatures.py
│       └── providers/
│           ├── __init__.py
│           ├── base.py
│           ├── claude_code.py
│           ├── gemini.py
│           ├── hermes.py
│           ├── local_git.py
│           ├── obsidian.py
│           └── opencode.py
```

## 2. Configuration Management
Use `pydantic-settings` for robust, decoupled configuration.

- **File**: `src/recall/config.py`
- **Class**: `Settings(BaseSettings)`
- **Env File**: `.env.local`
- **Fields**:
  - `notebook_path: str = "~/Notebook"`
  - `workspace_path: str = "~/Workspace"`
  - `dspy_provider: str = "openrouter"`
  - `dspy_model: str = "openai/gpt-4o-mini"`
  - `openrouter_api_key: Optional[SecretStr]`
  - `openai_api_key: Optional[SecretStr]`
  - `anthropic_api_key: Optional[SecretStr]`

## 3. TUI (Rich Dashboard)
Implement a visually rich, non-interactive dashboard for data extraction and correlation.

- **File**: `src/recall/tui.py`
- **Features**:
  - `Layout`: Top bar (status), main area (split), bottom bar (footer).
  - `Live`: Continuous update during extraction.
  - `Table`: For displaying sessions found on different platforms.
  - `Panel`: For rendering the AI-generated narrative and next actions.
  - `Syntax`: Highlight JSON or code snippets where applicable.

## 4. Implementation Details

### Refactoring `MultiSourceCorrelator`
- Update `__init__` to accept `Settings`.
- Replace `os.environ.get` calls with `self.settings`.
- Ensure all internal calls to providers/modules use the injected settings.

### Refactoring CLI
- Use `typer` (optional, but requested "sweet looking TUI", `rich` + `typer` is a common combo. I'll stick with `argparse` or `click` if `typer` is not requested, but `typer` is very "modern"). Wait, I'll stick to updating the current `argparse` or just use `typer` if I can justify it. The user didn't ask for `typer`, but it fits the "proper uv project" and "sweet TUI" theme. Actually, I'll stick to `argparse` to minimize unnecessary changes unless `typer` is preferred.
- Add a `--tui` flag to the `extract` and `correlate` commands.
- If `--tui` is set, use `RecallTUI` to display progress and results.

## 5. Migration Plan
1.  **Initialize uv**: `uv init --lib`.
2.  **Restructure**: Create `src/recall/` and move files.
3.  **Dependencies**: `uv add rich pydantic-settings python-dotenv dspy-ai httpx`.
4.  **Config**: Write `src/recall/config.py`.
5.  **Core Refactor**: Update `src/recall/core.py` and `src/recall/models.py`.
6.  **TUI Implementation**: Write `src/recall/tui.py`.
7.  **CLI Update**: Update `src/recall/cli.py`.
8.  **Verification**: Test `recall extract --tui` and `recall correlate --tui`.
