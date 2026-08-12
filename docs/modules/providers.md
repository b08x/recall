# Provider Implementations

**Location**: `src/recall/providers/`
**Confidence**: EXTRACTED

## Transformation Contract

The providers module **transforms** platform-specific session formats (JSON files, SQLite databases, filesystem structures) **into** unified `ParsedSession` objects **through** provider-specific extraction logic that normalizes heterogeneous data sources **when** the provider's data files are present; gracefully degrades for unavailable platforms.

> The provider implementations work like cultural attaches at an embassy — each one **understands the local customs and file formats** of their assigned platform (Gemini CLI, Claude Code, Hermes) and **translates** them into a common diplomatic language (`ParsedSession`) that the rest of the system can understand, **while** the base class ensures that missing platforms don't halt the extraction pipeline.

## Responsibilities

- Discover session files from platform-specific locations
- Parse platform-specific formats into unified `ParsedSession` objects
- Normalize message structures across platforms
- Handle provider-specific quirks (compact mode, thinking blocks, tool calls)
- Support multiple platforms: Gemini CLI, Claude Code, Hermes, OpenCode, Local Git, Obsidian
- Report usage metrics and error details for failed extractions

## Key Components

| Component | Type | Transformation / Role | Confidence |
|-----------|------|-----------------------|------------|
| `BaseProvider` | ABC | **defines** the provider interface: `discover()` + `parse()` | EXTRACTED |
| `GeminiProvider` | class | **extracts** sessions from `~/.gemini/tmp/<hash>/chats/*.json` | EXTRACTED |
| `ClaudeCodeProvider` | class | **extracts** sessions from `~/.claude/projects/*` | EXTRACTED |
| `HermesProvider` | class | **extracts** sessions from `~/.hermes/state.db` and JSON files | EXTRACTED |
| `OpenCodeProvider` | class | **extracts** sessions from `~/.local/share/opencode/*` | EXTRACTED |
| `ObsidianProvider` | class | **extracts** notes from `~/Notebook` markdown files | EXTRACTED |
| `LocalGitProvider` | class | **discovers** git repositories and extracts commit history | EXTRACTED |
| `SessionUsage` | dataclass | **aggregates** token usage across all providers | EXTRACTED |

## Dependencies

**Requires**:
- `recall.models` — `ParsedSession`, `ParsedMessage`, `SessionUsage` data structures
- Platform-specific knowledge (file paths, JSON schemas, SQLite schemas)

**Enables**:
- `Core Pipeline` (`MultiSourceCorrelator`) — provides extracted sessions for analysis
- `DB Layer` — persists sessions via `PersistManager`
- `Context Layer` — provides git context from `LocalGitProvider`

## Interactions

```mermaid
flowchart LR
    MSC["MultiSourceCorrelator"] -->|extract()| GP["GeminiProvider"]
    MSC -->|extract()| CP["ClaudeCodeProvider"]
    MSC -->|extract()| HP["HermesProvider"]
    MSC -->|extract()| OP["OpenCodeProvider"]
    GP -->|ParsedSession| MSC
    CP -->|ParsedSession| MSC
    HP -->|ParsedSession| MSC
    LP["LocalGitProvider"] -->|commits| MSC
    OP["ObsidianProvider"] -->|notes| CSM["ContextSourceManager"]
```

## What Users / Developers Experience

- **First encounter**: Developers **typically focus on** the provider classes for debugging extraction issues or adding new platform support
- **After regular use**: Provider-specific path configurations **may need** adjustment for non-standard installations
- **Error handling**: Failed extractions are logged with `error()` and may be routed to the DLQ
- **Rate limiting**: Each provider uses named rate limiters (`"gemini"`, `"hermes"`, `"claude"`) to prevent API abuse

## Known Limitations

**Works well when**: Provider data files follow expected formats and locations
**May struggle with**: Custom installations where paths differ from defaults; platforms with undocumented session formats
**Requires workarounds for**: Gemini CLI's hash-based directory structure; OpenCode's SQLite schema variations

## Code Snippets

### Extracting sessions from a specific platform
```python
from recall.providers.gemini import GeminiProvider
from recall.config import Settings

settings = Settings()
gemini = GeminiProvider()
sessions = gemini.extract(date_range={'start': ..., 'end': ...})
```

### Adding a new provider
```python
from recall.providers.base import BaseProvider
from recall.models import ParsedSession

class MyProvider(BaseProvider):
    def discover(self, date_range=None):
        # Find session files
        ...
    
    def parse(self, source_id):
        # Parse into ParsedSession
        return ParsedSession(id=..., ...)
```

## Ruby Pragmatist Insight

The provider implementations work like a team of interpreters at the UN — each one **specializes in the language and format** of their assigned platform, **translating** into a common schema that the rest of the system understands, **while** the abstract base class ensures that even missing platforms don't break the overall coordination, much like how the UN continues functioning even when some delegations are absent.
