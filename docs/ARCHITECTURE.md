# Recall Architecture Documentation

> **Recall** is a multi-platform session extraction and correlation system that transforms disparate AI assistant interactions into unified insights, contextual correlations, and actionable narratives.

This document provides comprehensive technical documentation of the Recall project architecture, data models, processing pipelines, and integration points.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Layers](#architecture-layers)
3. [Core Components](#core-components)
4. [Data Models](#data-models)
5. [Processing Pipelines](#processing-pipelines)
6. [Storage Layer](#storage-layer)
7. [Provider Integration](#provider-integration)
8. [Context Enhancement System](#context-enhancement-system)
9. [AI & Analysis Modules](#ai--analysis-modules)
10. [Resilience Features](#resilience-features)
11. [Configuration](#configuration)
12. [Performance Considerations](#performance-considerations)

---

## System Overview

### Purpose

Recall solves the fundamental problem of **workstream fragmentation** in modern development. As developers interact with multiple AI assistants (Gemini CLI, Claude Code, Hermes, OpenCode) alongside traditional tools (Git, GitHub, Obsidian), their work becomes scattered across disparate data sources with no unified view.

Recall:
- **Extracts** sessions from all supported platforms
- **Normalizes** them to a common schema
- **Analyzes** content using DSPy for insight extraction
- **Enriches** insights with contextual information from documentation and code history
- **Correlates** activities across platforms and time
- **Persists** everything in a searchable, queryable database

### High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         PROVIDER LAYER                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐  │
│  │  Gemini  │ │  Claude  │ │  Hermes  │ │ OpenCode │ │  Git    │  │
│  │  CLI    │ │  Code    │ │          │ │          │ │ (local) │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬────┘  │
└───────┼────────────┼────────────┼────────────┼────────────┼─────────┘
        │              │              │              │              │
        ▼              ▼              ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      EXTRACTION & NORMALIZATION                      │
│                    (MultiSourceCorrelator)                          │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  BaseProvider.HTTP -> extract() -> parse() -> ParsedSession      │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                          ANALYSIS LAYER                               │
│  ┌──────────────────────┐  ┌──────────────────────┐               │
│  │ SessionAnalysisModule │  │ SessionInsightModule   │               │
│  │   - Topic extraction  │  │   - Categorized insights│               │
│  │   - Files touched     │  │   - Importance scoring │               │
│  │   - Key actions       │  │   - Theme identification│              │
│  └──────────────────────┘  └──────────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CONTEXT ENHANCEMENT                            │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │ ObsidianContext   │  │ GitContextSource   │  │ QMDContext      │  │
│  │   - Note search   │  │   - Commit history │  │   - QMD queries │  │
│  │   - Tag matching  │  │   - File patterns  │  │   - KB search   │  │
│  └──────────────────┘  └──────────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                        CORRELATION LAYER                             │
│                    (CorrelationModule + DSPy)                       │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ TimelineSynthesizer -> Narrative generation                     │  │
│  │ OneThingGenerator -> Highest-leverage next action               │  │
│  │ CommitSessionCorrelator -> Link commits to sessions             │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                     │
        ┌────────────────────────────────┼─────────────────────────┐
        ▼                            ▼                           ▼
┌───────────────┐           ┌───────────────┐           ┌──────────────┐
│  SQLiteStore   │           │  VectorStore   │           │   DLQ        │
│  - Sessions    │           │  - ChromaDB    │           │  - Failed     │
│  - Messages    │           │  - Embeddings  │           │  - Retryable  │
│  - Analysis    │           │  - Semantic    │           │  - Persistent │
│  - Insights    │           │    search      │           │    queue     │
└───────────────┘           └───────────────┘           └──────────────┘
```

---

## Architecture Layers

### 1. Provider Layer

**Responsibility**: Extract raw session data from various platforms and normalize it to the `ParsedSession` schema.

**Components**:
- `BaseProvider` (ABC) - Abstract interface
- `GeminiProvider` - Extracts from `~/.gemini/tmp/<hash>/chats/*.json`
- `ClaudeCodeProvider` - Extracts from `~/.claude/projects/*`
- `HermesProvider` - Extracts from `~/.hermes/state.db` and JSON files
- `OpenCodeProvider` - Extracts from `~/.local/share/opencode/*`
- `ObsidianProvider` - Extracts notes from Obsidian vault
- `LocalGitProvider` - Extracts commits from local repositories

**Key Features**:
- Discovery of session files based on date ranges
- Platform-specific parsing logic
- Normalization to unified message/tool call structures
- Usage metric extraction

### 2. Core Orchestration Layer

**Responsibility**: Coordinate extraction, analysis, enrichment, and persistence.

**Main Component**: `MultiSourceCorrelator` (`src/recall/core.py`)

**Key Features**:
- Thread-safe parallel extraction via `ThreadPoolExecutor`
- Provider-specific named rate limiters
- Pre-flight token estimation
- Dead Letter Queue management
- Timeline synthesis
- DSPy configuration management

### 3. AI/Analysis Layer

**Responsibility**: Transform raw session content into structured insights.

**Components**:
- `SessionAnalysisModule` - Extracts topics, files, key actions
- `SessionInsightModule` - Generates categorized insights with importance scores
- `CorrelationModule` - Multi-stage correlation pipeline
- `ContextEnhancementModule` - Enriches insights with contextual information
- `ContextualChunker` - Intelligent session chunking for LLM processing

**Framework**: DSPy (Stanford's declarative LLM programming framework)

### 4. Context Enhancement Layer

**Responsibility**: Augment session insights with relevant external context.

**Components**:
- `ContextSourceManager` - Orchestrates context sources
- `ContextSource` (ABC) - Plugin interface
- `ObsidianContextSource` - Searches Obsidian vault for relevant notes
- `GitContextSource` - Finds relevant Git commits and patterns
- `QMDContextSource` - Queries QMD knowledge base

### 5. Storage Layer

**Responsibility**: Persistent storage and retrieval.

**Components**:
- `PersistenceManager` - Orchestrates dual-write transactions
- `SQLiteStore` - Relational storage (WAL mode, connection pooling)
- `VectorStore` - ChromaDB-based semantic search
- `DeadLetterQueue` - Persistent failure tracking

### 6. Interface Layer

**Responsibility**: User interaction.

**Components**:
- `cli.py` - Command-line interface with argparse
- `tui.py` - Rich-based terminal dashboard
- Configuration via Pydantic-Settings

**Module Docs**: See [`core.md`](core.md), [`cli.md`](cli.md), [`config.md`](config.md) for detailed component documentation.

---

## Core Components

### MultiSourceCorrelator

**Location**: `src/recall/core.py`

**Purpose**: Primary orchestrator that coordinates all major operations.

**Key Methods**:

| Method | Description |
|--------|-------------|
| `extract_all()` | Main extraction pipeline with parallel processing |
| `analyze_session_topics()` | DSPy-based topic extraction |
| `analyze_session_insights()` | DSPy-based insight extraction |
| `build_timeline()` | Unified timeline from multiple sources |
| `correlate_with_dspy()` | AI-powered correlation synthesis |
| `retry_dlq()` | Dead Letter Queue retry logic |
| `configure_dspy()` | DSPy language model configuration |

**Concurrency Model**:
- Uses `ThreadPoolExecutor` for parallel session processing
- Each session processed independently with thread-safe rate limiting
- Connection pooling via thread-local SQLite connections
- Automatic retry with exponential backoff for transient failures

**Rate Limiting Strategy**:
- Global default RPM configurable via `requests_per_minute`
- Per-provider named limiters (e.g., "embeddings", "github", "context_enhancement")
- Provider-specific RPM via `set_limiter_rpm(name, rpm)`
- Thread-safe `RateLimiter` class using time-based waiting

### PersistenceManager

**Location**: `src/recall/db/manager.py`

**Purpose**: Coordinates atomic dual-writes to SQLite and ChromaDB.

**Dual-Write Resilience**:
```
1. Save to SQLite (relational data)          ┐
   ├─ Commit SQLite transaction               │
   │  └─ If fail: rollback, raise exception   │
   │                                             │
2. Index in ChromaDB (vector embeddings)       ├─ Transactional safety
   ├─ If fail: mark SQLite indexing_status='failed'
   │  └─ SQLite data persists, can be reconciled later
   │
3. Update SQLite indexing_status='completed'  └─
```

**Reconciliation**:
- `reconcile_failed_vectors()` - Retries sessions marked as failed
- Automatically triggered or called via CLI
- Uses `overwrite=True` to clean up partial vector state

---

## Data Models

### Core Data Classes

All data models are defined in `src/recall/models.py` using Python dataclasses.

#### Session Hierarchy

```
ParsedSession (Top-level container)
├── id: str (unique session identifier)
├── project_path: str
├── project_name: str
├── source_tool: str (gemini-cli, claude, hermes, opencode)
├── started_at: datetime
├── ended_at: datetime
├── message_count: int
├── user_message_count: int
├── assistant_message_count: int
├── tool_call_count: int
├── git_branch: Optional[str]
├── claude_version: Optional[str]
├── usage: SessionUsage
└── messages: List[ParsedMessage]

SessionUsage
├── total_input_tokens: int
├── total_output_tokens: int
├── cache_creation_tokens: int
├── cache_read_tokens: int
├── estimated_cost_usd: float
├── models_used: List[str]
├── primary_model: str
└── usage_source: str

ParsedMessage
├── id: str
├── session_id: str
├── type: Literal['user', 'assistant', 'system']
├── content: str
├── thinking: Optional[str] (internal reasoning)
├── tool_calls: List[ToolCall]
├── tool_results: List[ToolResult]
├── usage: Optional[Dict]
├── timestamp: datetime
└── parent_id: Optional[str]

ToolCall
├── id: str
├── name: str
└── input: Dict[str, Any]

ToolResult
├── tool_use_id: str
└── output: str
```

#### Analysis & Insights

```
SessionAnalysis
├── session_id: str
├── topics: List[str]
├── files_touched: List[str]
├── key_actions: List[str]
└── analyzed_at: datetime

SessionInsight (Single insight)
├── category: str (TECHNICAL, PROCEDURAL, STRATEGIC, BLOCKER)
├── content: str
└── importance: float (0.0-1.0)

SessionInsights (Container)
├── session_id: str
├── insights: List[SessionInsight]
├── primary_theme: str
├── confidence: float
└── generated_at: datetime
```

#### Correlation

```
CorrelationResult
├── id: str
├── start_date: datetime
├── end_date: datetime
├── narrative: str
├── workstreams: List[str]
├── next_actions: List[str]
├── one_thing: str
├── one_thing_reasoning: str
├── session_ids: List[str]
└── created_at: datetime
```

#### Context Enhancement

```
ContextMatch
├── source_type: str (obsidian, git, qmd)
├── content: str
├── relevance_score: float (0.0-1.0)
├── match_reasons: List[str]
└── metadata: Dict[str, Any]

EnhancedSessionInsights
├── session_id: str
├── base_insights: SessionInsights
├── contextual_insights: List[ContextualInsight]
├── knowledge_gaps_filled: List[str]
├── suggested_references: List[ContextMatch]
├── enhancement_metadata: Dict
└── enhanced_at: datetime

ContextualInsight (extends SessionInsight)
├── supporting_context: List[ContextMatch]
├── context_sources_used: List[str]
└── enhancement_confidence: float
```

---

## Processing Pipelines

### Extraction Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│  extract_all(days, platforms, analyze, overwrite, enhance_with_context)│
└────────────────────────┬────────────────────────────────────────┘
                         │
    ┌────────────────────┼────────────────────┐
    ▼                    ▼                    ▼
┌──────────┐      ┌──────────┐          ┌──────────┐
│ Discover  │      │ Discover  │          │ Discover  │
│ Session   │      │ Session   │          │ Notes     │
│ Files     │      │ Files     │          │           │
└────┬──────┘      └────┬──────┘          └────┬──────┘
     │                  │                     │
     ▼                  ▼                     ▼
┌──────────┐      ┌──────────┐          ┌──────────┐
│ Parse     │      │ Parse     │          │ Parse     │
│ -> Session│      │ -> Session│          │ -> Notes  │
└────┬──────┘      └────┬──────┘          └────┬──────┘
     │                  │                     │
     └──────────────────┼─────────────────────┘
                          │
                          ▼
                 ┌─────────────────┐
                 │ ThreadPoolExecutor│
                 │ (max_workers=N)  │
                 └────────┬────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   ┌──────────┐     ┌──────────┐         ┌──────────┐
   │Process   │     │Process   │         │Process   │
   │Session A │     │Session B │    ...  │Session N │
   └────┬──────┘     └────┬──────┘         └────┬──────┘
        │                 │                 │
        ▼                 ▼                 ▼
   ┌─────────────────────────────────────────────┐
   │  _process_single_session(session, platform, ...)│
   │  1. Analyze (optional)                         │
   │     ├─ SessionAnalysisModule -> topics, files │
   │     └─ SessionInsightModule -> insights        │
   │  2. Context Enhancement (optional)            │
   │     └─ ContextSourceManager -> enhanced insights│
   │  3. Persist                                   │
   │     └─ PersistenceManager.persist_session()   │
   └─────────────────────────────────────────────┘
```

**Parallel Processing Flow**:
1. Discover session files from all requested platforms
2. For each platform, parse files into `ParsedSession` objects
3. Submit all sessions to thread pool for parallel processing
4. Each thread: analyze → enhance → persist independently
5. Main thread waits for completion, handles retries, manages DLQ

### Analysis Pipeline (Per Session)

```
_input: ParsedSession_ful
     │
     ▼
┌─────────────────────────────────────┐
│ ContextualChunker.chunk_session()    │
│ - Split by time gaps (>30 min)        │
│ - Split by length (>6000 chars)       │
│ - Preserve tool results              │
│ - Truncate oversized messages        │
└────────────────┬────────────────────┘
                 │
                 ▼
    ┌─────────────────────────────────────────┐
    │ For each chunk:                        │
    │   SessionAnalysisModule.forward(chunk)  │
    │   ├─ SessionTopicExtractor (DSPy)       │
    │   │  └─ Extract: topics, files_touched,  │
    │   │     key_actions                       │
    │   └─ Aggregate results across chunks     │
    │                                              │
    │   SessionInsightModule.forward(chunk)    │
    │   ├─ SessionInsightExtractor (DSPy)     │
    │   │  └─ Extract: insights (List[Insight]) │
    │   │     - category, content, importance  │
    │   │     - primary_theme, confidence       │
    │   └─ Aggregate and deduplicate            │
    └─────────────────────────────────────────┘
                 │
                 ▼
    ┌─────────────────────────────────────────┐
    │ Context Enhancement (optional)            │
    │   ContextSourceManager.enhance_insights() │
    │   ├─ Parallel context source queries     │
    │   │  ├─ ObsidianContextSource            │
    │   │  │  └─ Note search, tag matching     │
    │   │  ├─ GitContextSource                 │
    │   │  │  └─ Commit history, file patterns │
    │   │  └─ QMDContextSource                 │
    │   │     └─ Knowledge base queries        │
    │   ├─ Filter by relevance threshold       │
    │   ├─ Sort by score                       │
    │   └─ Create EnhancedSessionInsights       │
    └─────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│ PersistenceManager.persist_session()         │
│  1. Save to SQLiteStore                       │
│     ├─ sessions table                         │
│     ├─ messages table                        │
│     ├─ tool_calls table                       │
│     └─ session_analysis / session_insights    │
│  2. Index in VectorStore                      │
│     ├─ Chunk text via ContextualChunker       │
│     ├─ Generate embeddings                    │
│     └─ Store in ChromaDB                      │
│  3. Update indexing_status                   │
└─────────────────────────────────────────────┘
```

### Correlation Pipeline

```
_input: Dict[str, List[ParsedSession]], days_
     │
     ▼
┌─────────────────────────────────────────────┐
│ MultiSourceCorrelator.build_timeline()       │
│  ├─ Normalize all items to timeline events    │
│  │  ├─ session -> type: "session"             │
│  │  ├─ note -> type: "note"                   │
│  │  └─ commit -> type: "commit"               │
│  └─ Sort by timestamp                         │
└────────────────────────┬────────────────────┘
                         │
                         ▼
          ┌──────────────────────────────────────┐
          │ fetch_github_data() (optional)          │
          │  - gh CLI API calls                    │
          │  - Rate limited, retried               │
          │  - Returns commits, PRs                │
          └──────────────┬───────────────────────┘
                         │
          ┌──────────────────────────────────────┐
          │ fetch_local_git_data()                  │
          │  - Scan workspace repositories         │
          │  - Parse git logs                       │
          │  - Extract commits                      │
          └──────────────┬───────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────┐
│ CorrelationModule.forward()                   │
│  1. TimelineSynthesizer (DSPy)                 │
│     ├─ Input: sessions, commits, file_changes  │
│     └─ Output: narrative, workstreams, actions │
│  2. OneThingGenerator (DSPy)                  │
│     ├─ Input: recent_activity, workstreams     │
│     └─ Output: one_thing, reasoning            │
│  3. Context summary extraction (if enhanced)  │
└─────────────────────────────────────────────┘
                         │
                         ▼
              ┌─────────────────────────┐
              │ CorrelationResult        │
              │ - narrative              │
              │ - workstreams            │
              │ - next_actions           │
              │ - one_thing              │
              │ - one_thing_reasoning    │
              └─────────────────────────┘
```

---

## Storage Layer

### SQLite Schema

**Location**: `src/recall/db/sqlite_store.py`

**Tables**:

```sql
-- Core session data
sessions (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    project_name TEXT,
    project_path TEXT,
    summary TEXT,
    generated_title TEXT,
    started_at DATETIME,
    ended_at DATETIME,
    message_count INTEGER DEFAULT 0,
    git_branch TEXT,
    source_tool TEXT DEFAULT 'unknown',
    metadata TEXT,
    indexing_status TEXT DEFAULT 'pending'
)

-- Session messages
messages (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    type TEXT CHECK(type IN ('user', 'assistant', 'system')),
    content TEXT,
    thinking TEXT,
    timestamp DATETIME,
    parent_id TEXT,
    usage TEXT
)

-- Tool calls within messages
tool_calls (
    id TEXT PRIMARY KEY,
    message_id TEXT REFERENCES messages(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    input TEXT
)

-- Normalized topics (many-to-many with sessions)
topics (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)
session_topics (session_id, topic_id, PRIMARY KEY (session_id, topic_id))

-- Normalized file paths (many-to-many with sessions)
file_paths (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE NOT NULL)
session_files (session_id, file_id, PRIMARY KEY (session_id, file_id))

-- Session analysis
session_analysis (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    key_actions TEXT,
    analyzed_at DATETIME DEFAULT CURRENT_TIMESTAMP
)

-- Session insights
session_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    importance REAL DEFAULT 0.5,
    primary_theme TEXT,
    confidence REAL,
    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)

-- Correlations
correlations (
    id TEXT PRIMARY KEY,
    start_date DATETIME,
    end_date DATETIME,
    narrative TEXT,
    workstreams TEXT,
    next_actions TEXT,
    one_thing TEXT,
    one_thing_reasoning TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)

-- Correlation to session mapping
correlation_sessions (correlation_id, session_id, PRIMARY KEY (correlation_id, session_id))

-- Dead Letter Queue
dlq (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    payload TEXT NOT NULL,
    error TEXT,
    failed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    retry_count INTEGER DEFAULT 0
)
```

**WAL Mode**: All SQLite connections use `PRAGMA journal_mode=WAL;` for:
- Concurrent read/write access
- Better performance under high load
- Automatic checkpointing

**Connection Pooling**: Thread-local connections via `threading.local()` to:
- Avoid connection instantiation overhead
- Support concurrent operations safely
- Automatically handle stale connections

### Vector Store (ChromaDB)

**Location**: `src/recall/db/vector_store.py`

**Features**:
- Persistent collection storage on disk
- Custom embedding functions for multiple providers:
  - `DSPyEmbeddingFunction` - OpenAI, Mistral, HuggingFace via LiteLLM
  - `OllamaEmbeddingFunction` - Local Ollama embedding models
- Token-aware chunking with safety buffers
- Automatic dimension compatibility checking

**Embedding Models Supported**:
- Ollama: `snowflake-arctic-embed2:568m`, `nomic-embed-text:latest`, etc.
- OpenAI: `text-embedding-3-small`, `text-embedding-3-large`
- Mistral: `mistral-embed`
- HuggingFace: Various sentence-transformers

**Safety Features**:
- 10% token buffer to account for tokenizer differences
- Character-based fallback when tiktoken unavailable
- Truncation of oversized chunks before embedding
- Automatic retry with exponential backoff

---

## Provider Integration

### Provider Architecture

All providers inherit from `BaseProvider` (ABC) with:

```python
class BaseProvider(ABC):
    @abstractmethod
    def discover(self, date_range: Optional[Dict[str, datetime]] = None, **kwargs) -> List[str]:
        """Discover session files/IDs."""
        pass
    
    @abstractmethod
    def parse(self, source_id: str) -> Optional[ParsedSession]:
        """Parse a single session source."""
        pass
    
    def extract(self, date_range: Dict[str, datetime], **kwargs) -> List[ParsedSession]:
        """Extract and parse sessions within date range."""
        # Default implementation calls discover() then parse() for each
```

### Provider-Specific Details

#### Gemini Provider

**Source**: `~/.gemini/tmp/<project_hash>/chats/*.json`

**Structure**:
```json
{
  "sessionId": "...",
  "startTime": 1234567890,
  "lastUpdated": 1234567890,
  "messages": [
    {
      "id": "...",
      "type": "user|gemini|info",
      "content": "...",
      "timestamp": 1234567890,
      "toolCalls": [...],
      "toolResults": [...]
    }
  ]
}
```

**Normalization**:
- `type: "gemini"` → `type: "assistant"`
- `type: "user"` → `type: "user"`
- `type: "info"` → `type: "system"`
- Project info from `.project_root` file

#### Claude Code Provider

**Source**: `~/.claude/projects/*/conversations/*`

**Features**:
- Handles Claude's conversation format
- Extracts project path resolution
- Processes tool calls and results
- Captures subagent session associations

#### Hermes Provider

**Source**: `~/.hermes/state.db` (SQLite) + JSON files

**Features**:
- Hybrid SQLite + filesystem extraction
- Parses Hermes's structured session format
- Normalizes tool execution data

#### OpenCode Provider

**Source**: `~/.local/share/opencode/*/sessions/*`

**Features**:
- Handles OpenCode's JSONL session format
- Extracts workspace and project metadata
- Processes tool invocations

#### Obsidian Provider

**Source**: Obsidian vault path (configurable)

**Features**:
- Scans for `.md` files
- Parses YAML frontmatter for metadata
- Extracts tags from content and frontmatter
- Respects modification time for date filtering

#### Local Git Provider

**Source**: Local Git repositories in workspace

**Features**:
- Discovers repositories in workspace path
- Parses commit history via `git log`
- Extracts commit messages, authors, timestamps
- Filters by date range

### Provider Discovery Strategy

Each provider implements its own discovery logic:

```python
# Example: GeminiProvider.discover()
def discover(self, date_range: Optional[Dict[str, datetime]] = None, 
            project_filter: Optional[str] = None) -> List[str]:
    # 1. Load project mappings from ~/.gemini/projects.json
    # 2. Scan ~/.gemini/tmp/<hash>/chats/ for *.json files
    # 3. Filter by project_filter if specified
    # 4. Filter by modification time if date_range specified
    # 5. Return list of file paths
    pass
```

---

## Context Enhancement System

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ContextSourceManager                            │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Sources: Dict[str, ContextSource]                              │  │
│  │  - obsidian: ObsidianContextSource                             │  │
│  │  - git: GitContextSource                                       │  │
│  │  - qmd: QMDContextSource                                       │  │
│  └─────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
                  ┌──────────────────────┐
                  │ enhance_insights()    │
                  │  1. Initialize sources │
                  │  2. Parallel query    │
                  │  3. Filter & rank      │
                  │  4. Create enhanced   │
                  │     insights          │
                  └──────────────────────┘
```

### Context Source Interface

```python
class ContextSource(ABC):
    @abstractmethod
    async def find_relevant_content(self, insights: SessionInsights,
                                   session_context: Dict[str, Any]) -> List[ContextMatch]:
        """Find context relevant to session insights."""
        pass
    
    @property
    @abstractmethod
    def source_type(self) -> str:
        """Unique identifier for this context source."""
        pass
    
    async def is_available(self) -> bool:
        """Check if source is available and configured."""
        return True
```

### Obsidian Context Source

**Location**: `src/recall/providers/context/obsidian.py`

**Features**:
- Caches notes with 5-minute TTL
- Hybrid matching strategy:
  - Title matching (highest weight: 0.4)
  - Tag matching (weight: 0.3)
  - Content keyword matching (weight: 0.2)
  - File name overlap (weight: 0.3)
  - Temporal relevance (recent notes bonus: 0.1)
  - Theme matching (weight: 0.3)
- Limits to notes modified in last 30 days (configurable)
- Skips hidden directories (`.obsidian`, etc.)

**Matching Weights**:
```python
weights = {
    "title_match": 0.4,
    "tag_match": 0.3,
    "content_keyword": 0.2,
    "file_overlap": 0.3,
    "temporal_bonus": 0.1
}
```

### Git Context Source

**Features**:
- Searches commit history for relevant patterns
- Matches based on file paths, commit messages
- Provides contextual information about code changes
- Supports both local and remote repositories

### Context Match Structure

```python
@dataclass
class ContextMatch:
    source_type: str  # "obsidian", "git", "qmd"
    content: str  # The relevant content text
    relevance_score: float  # 0.0-1.0
    match_reasons: List[str]  # Why this matched
    metadata: Dict[str, Any]  # Source-specific metadata
```

---

## AI & Analysis Modules

### DSPy Integration

Recall uses **DSPy** (Stanford's declarative LLM programming framework) for all AI-powered analysis. DSPy provides:
- Structured output via Pydantic models
- Chain-of-Thought reasoning
- Automatic prompt optimization
- Multi-provider support (OpenAI, Mistral, Ollama, etc.)

**Configuration**:
```python
# Settings
dspy_provider: str = "openrouter"  # openrouter, openai, ollama, mistral
dspy_model: str = "openai/gpt-4o-mini"
dspy_insights_model: Optional[str] = None  # Override for deep insights
dspy_insights_provider: Optional[str] = None  # Override provider

# API Keys
openrouter_api_key: Optional[SecretStr]
openai_api_key: Optional[SecretStr]
mistral_api_key: Optional[SecretStr]
```

### Signatures (DSPy Prompts)

**Location**: `src/recall/ai/signatures.py`

#### SessionTopicExtractor

Extracts primary topics, files touched, and key actions from session content.

**Input**:
- `session_content: str` - Session transcript
- `context_metadata: str` - Platform, project, date context

**Output**:
- `topics: List[str]` - 3-5 main topics
- `files_touched: List[str]` - File paths modified/analyzed
- `key_actions: List[str]` - Kinetic actions (commits, tests, fixes)

**Special Instructions**:
- Focus ONLY on user's actual work
- Ignore recall application's internal structure
- Differentiate "thinking" vs "doing" based on tool usage

#### SessionInsightExtractor

Extracts categorized insights from session transcripts.

**Input**:
- `session_content: str` - Combined session messages
- `context_metadata: str` - Context info

**Output**:
- `insights: List[Insight]` - Categorized insights
  - `category: TECHNICAL | PROCEDURAL | STRATEGIC | BLOCKER`
  - `content: str` - 2-3 sentence description
  - `importance: float` - 0.0-1.0
- `primary_theme: str` - Core unifying theme
- `confidence: float` - 0.0-1.0

**Special Instructions**:
- Analyze conversation, tool outputs, internal thoughts
- TECHNICAL WORK IS SUBSTANTIVE
- Focus on USER'S work, not recall tool structure

#### TimelineSynthesizer

Synthesizes coherent narrative from multiple data sources.

**Input**:
- `sessions: List[SessionInput]` - Session data
- `commits: List[CommitInput]` - Git commits
- `file_changes: List[FileChangeInput]` - File modifications
- `context_summary: Optional[str]` - Context enhancement summary

**Output**:
- `narrative: str` - Coherent activity narrative
- `workstreams: List[str]` - Distinct workstreams
- `next_actions: List[str]` - Suggested next actions
- `strategic_insights: List[str]` - Strategic insights

#### OneThingGenerator

Generates the single highest-leverage next action.

**Input**:
- `recent_activity: str` - Summary of recent work
- `workstreams: List[str]` - Active workstreams
- `open_questions: List[str]` - Unresolved blockers

**Output**:
- `one_thing: str` - Most important next action
- `reasoning: str` - Why this action is highest leverage

#### ContextEnhancementSignature

Enhances insights using contextual information.

**Input**:
- `original_insights: str` - JSON of SessionInsights
- `context_matches: List[ContextMatchInput]` - Relevant context
- `session_metadata: str` - Additional context

**Output**:
- `enhanced_insights: List[EnhancedInsightOutput]` - Enhanced insights
- `knowledge_gaps_filled: List[str]` - Addressed knowledge gaps
- `strategic_recommendations: List[str]` - Strategic guidance
- `confidence_assessment: str` - Quality assessment

### Chunking Strategy

**Location**: `src/recall/ai/chunking.py`

**ContextualChunker** intelligently splits sessions based on:

1. **Temporal Boundaries**: Split if gap > 30 minutes between messages
2. **Length Boundaries**: Split if chunk would exceed `max_chunk_chars` (default: 6000)
3. **Message Type**: Prefer splitting on user messages
4. **Oversized Messages**: Truncate single messages > max_chunk_chars

**Message Formatting**:
```
[USER] 14:30:00
Content here

[thinking]
Internal reasoning
[/thinking]

Tool Call: tool_name({'arg': 'value'})
Tool Result: output here
```

**Tool Result Handling**:
- Included by default (`include_tool_results=True`)
- Truncated to `max_tool_result_chars` (default: 2000)
- Can be disabled for shorter context

---

## Resilience Features

### Rate Limiting

**Location**: `src/recall/utils/limiter.py`

**Features**:
- Thread-safe rate limiting via `threading.Lock`
- Configurable requests per minute (RPM) per provider
- Named limiters for different services
- Global default with per-provider overrides

**Usage**:
```python
# Global configuration
set_global_rpm(20)  # 20 requests/minute default
set_limiter_rpm("embeddings", 500)  # 500 RPM for embeddings

# In code
def process_session():
    limiter = get_limiter("gemini")
    limiter.wait()  # Block if rate limited
    # ... make request ...
```

**Implementation**:
```python
class RateLimiter:
    def __init__(self, requests_per_minute: int, name: str = "default"):
        self.interval = 60.0 / requests_per_minute
        self.last_call = 0.0
        self._lock = threading.Lock()
    
    def wait(self):
        with self._lock:
            elapsed = time.time() - self.last_call
            wait_time = self.interval - elapsed
            if wait_time > 0:
                self.last_call = time.time() + wait_time
            else:
                self.last_call = time.time()
                wait_time = 0
        if wait_time > 0:
            time.sleep(wait_time)
```

### Retry Mechanism

**Location**: `src/recall/utils/limiter.py`

**Features**:
- Exponential backoff via `tenacity` library
- Configurable max attempts, min/max wait times
- Automatic logging of retry attempts

**Configuration**:
```python
retry_max_attempts: int = 5
retry_min_wait: float = 1.0  # seconds
retry_max_wait: float = 60.0  # seconds
```

**Usage**:
```python
@get_retry_decorator(
    max_attempts=5,
    min_wait=1.0,
    max_wait=60.0,
    exceptions=(HTTPError, ConnectionError)
)
def fetch_data():
    # This will be automatically retried on failure
    pass
```

### Dead Letter Queue (DLQ)

**Location**: SQLite `dlq` table + `MultiSourceCorrelator.retry_dlq()`

**Features**:
- Persistent storage of failed session payloads
- Survives application restarts
- Manual retry via CLI: `recall dlq --retry`
- Automatic retry count tracking
- Full payload serialization for recovery

**Schema**:
```sql
dlq (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    payload TEXT NOT NULL,  -- Serialized session + metadata
    error TEXT,
    failed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    retry_count INTEGER DEFAULT 0
)
```

**CLI Management**:
```bash
# List failed items
recall dlq --list

# Retry all items
recall dlq --retry

# Clear queue
recall dlq --clear
```

### Timeout Protection

**Features**:
- All external CLI calls have timeouts (GitHub, Git commands)
- Prevents thread starvation in parallel operations
- Configurable timeout values

**Usage**:
```python
# In MultiSourceCorrelator.fetch_github_data()
result = subprocess.run(
    ["gh", "api", ...],
    capture_output=True,
    timeout=30  # 30 second timeout
)
```

### Dual-Write Resilience

**Problem**: Atomic transaction across SQLite and ChromaDB is impossible.

**Solution**:
1. Write to SQLite first, mark as `indexing_status='pending'`
2. Commit SQLite transaction (data is safe)
3. Write to ChromaDB
4. If ChromaDB succeeds: update `indexing_status='completed'`
5. If ChromaDB fails: update `indexing_status='failed'`

**Recovery**:
- `PersistenceManager.reconcile_failed_vectors()` finds all 'failed' or 'pending' sessions
- Re-runs vector indexing for those sessions
- Preserves all SQLite data even if ChromaDB is down

### Token Estimation & Cost Management

**Location**: `MultiSourceCorrelator.estimate_session_tokens()`

**Features**:
- Pre-flight token estimation before LLM analysis
- Uses `tiktoken` for accurate counting (with fallback)
- Heuristic fallback: word + non-whitespace character counting
- Configurable warning threshold

**Implementation**:
```python
def estimate_session_tokens(self, sessions: List[ParsedSession]) -> int:
    if tiktoken_available:
        # Accurate counting
        return sum(len(encoding.encode(m.content)) for s in sessions for m in s.messages)
    else:
        # Fallback: regex-based estimation
        tokens = re.findall(r"\w+|[^\w\s]", content)
        return int(len(tokens) * 1.1)  # +10% overhead
```

**Usage**:
```python
# In CLI, before extraction with analysis
token_count = correlator.estimate_session_tokens(sessions_to_check)
if token_count > settings.token_warning_threshold:
    print(f"Warning: Estimated {token_count:,} tokens")
    if not confirm("Proceed?"):
        exit()
```

---

## Configuration

### Settings Structure

**Location**: `src/recall/config.py`

**Base Class**: `pydantic_settings.BaseSettings`

**Categories**:

#### Path Configuration
```python
notebook_path: str = "~/Notebook"           # Obsidian vault
workspace_path: str = "~/Workspace"          # Code workspace
db_path: str = "recall.db"                  # SQLite database
vector_db_dir: str = "./chroma_db"           # ChromaDB storage
```

#### DSPy Configuration
```python
dspy_provider: str = "openrouter"           # Provider: openrouter, openai, ollama, mistral
dspy_insights_provider: Optional[str]       # Override for insights
dspy_model: str = "openai/gpt-4o-mini"      # General analysis model
dspy_insights_model: Optional[str]           # Deep insight model
```

#### Embedding Configuration
```python
embedding_provider: str = "ollama"           # ollama, openai, mistral, huggingface
ollama_host: str = "http://tinybot:11434"     # Ollama server
embedding_model: str = "embeddinggemma:latest"  # Embedding model
embedding_max_tokens: int = 8192             # Max tokens for embeddings
chunk_max_chars: int = 6000                 # Chunk size for analysis
```

#### API Keys (All Optional, SecretStr)
```python
openrouter_api_key: Optional[SecretStr]
openai_api_key: Optional[SecretStr]
anthropic_api_key: Optional[SecretStr]
gemini_api_key: Optional[SecretStr]
mistral_api_key: Optional[SecretStr]
huggingface_api_key: Optional[SecretStr]
github_token: Optional[SecretStr]  # For GitHub API
```

#### Rate Limiting & Retry
```python
retry_max_attempts: int = 5
retry_min_wait: float = 1.0
retry_max_wait: float = 60.0
requests_per_minute: int = 20          # Global default RPM
embedding_rpm: int = 500                # Higher for local embeddings
max_workers: int = 10                  # Parallel extraction threads
reindex_workers: int = 1               # Re-indexing threads
token_warning_threshold: int = 100000 # Token count warning
```

#### Context Enhancement
```python
enable_context_enhancement: bool = True
context_sources: List[str] = ["obsidian", "git"]  # Enabled sources
max_context_matches_per_source: int = 3
context_relevance_threshold: float = 0.7
context_enhancement_timeout: float = 30.0
```

### Configuration Loading

**Priority**:
1. CLI arguments (highest)
2. Environment variables
3. `.env.local` file
4. Default values (lowest)

**File Format**:
```bash
# .env.local
OPENAI_API_KEY="sk-..."
MISTRAL_API_KEY="..."
RECALL_WORKSPACE_PATH="/path/to/workspace"
RECALL_NOTEBOOK_PATH="/path/to/notes"
```

---

## Performance Considerations

### Parallel Processing

- **ThreadPoolExecutor**: Used for session extraction and analysis
- **Max Workers**: Configurable via `max_workers` (default: 10)
- **Thread Safety**: 
  - Rate limiters use `threading.Lock`
  - SQLite uses WAL mode + thread-local connections
  - ChromaDB handles concurrent requests

### Memory Usage

- **Chunking**: Large sessions split into ~6000 char chunks
- **Streaming**: Messages processed one at a time within chunks
- **Caching**: Obsidian notes cached with 5-minute TTL
- **Connection Pooling**: SQLite connections reused per-thread

### Bottlenecks

1. **LLM API Calls**: Rate limited, can be slow for many sessions
2. **Embedding Generation**: Most time-consuming for vector indexing
3. **File I/O**: Discovery phase scans filesystem
4. **DSPy Initialization**: Model loading on first use

### Optimization Strategies

1. **Batching**: ChromaDB supports batch embedding
2. **Parallelism**: Multiple threads for independent sessions
3. **Caching**: Avoid re-processing unchanged files
4. **Lazy Loading**: Load DSPy models on-demand
5. **Connection Reuse**: Thread-local SQLite connections

### Benchmark Considerations

- **Extraction**: ~10-100 sessions/second (depends on file count)
- **Analysis**: ~1-5 sessions/minute (depends on LLM speed)
- **Embedding**: ~10-100 chunks/second (depends on model)
- **Search**: ~100-500ms per query (ChromaDB)

---

## Error Handling & Debugging

### Logging

**Location**: `src/recall/logging.py`

**Features**:
- Structured logging with timestamps
- Multiple levels: DEBUG, INFO, ERROR
- File output to `recall.log`
- Metric logging: `log_metric(name, value, unit)`
- Data logging: `log_data(name, dict)`
- Step timing: `step(name)` context manager

**Usage**:
```python
from recall.logging import debug, info, error, step, log_metric

debug("Processing session...")
info("Session processed successfully")
error("Failed to process: ...")

with step("session_analysis", detail="session-123"):
    # ... code ...
    # Automatically logs timing

log_metric("sessions_processed", 42, "count")
```

### Common Issues & Solutions

1. **Embedding Dimension Mismatch**
   - **Cause**: Changed embedding model with different dimension
   - **Solution**: Wipe vector store or re-embed existing data
   - **Detection**: `check_dimension_compatibility()` on startup

2. **API Rate Limiting**
   - **Cause**: Hitting provider rate limits
   - **Solution**: Configure appropriate RPM, use named limiters
   - **Recovery**: Automatic retry with exponential backoff

3. **Failed Sessions in DLQ**
   - **Cause**: Transient errors during processing
   - **Solution**: `recall dlq --retry` or `recall dlq --list` to inspect

4. **DSPy Configuration Failed**
   - **Cause**: Missing API keys or invalid model
   - **Solution**: Check settings, verify API keys

5. **ChromaDB Connection Issues**
   - **Cause**: ChromaDB server not running (if using client/server mode)
   - **Solution**: Use persistent mode (default) or start ChromaDB server

---

## File Structure

```
recall/
├── src/
│   └── recall/
│       ├── __init__.py           # Public exports
│       ├── cli.py                 # CLI entry point
│       ├── config.py              # Settings management
│       ├── context.py             # Context source manager
│       ├── core.py                # MultiSourceCorrelator
│       ├── logging.py             # Logging utilities
│       ├── models.py              # Data models
│       ├── tui.py                 # Terminal dashboard
│       │
│       ├── ai/
│       │   ├── __init__.py
│       │   ├── chunking.py         # ContextualChunker
│       │   ├── modules.py          # DSPy modules
│       │   └── signatures.py       # DSPy signatures
│       │
│       ├── db/
│       │   ├── __init__.py
│       │   ├── manager.py          # PersistenceManager
│       │   ├── sqlite_store.py     # SQLiteStore
│       │   └── vector_store.py     # VectorStore
│       │
│       ├── providers/
│       │   ├── __init__.py
│       │   ├── base.py             # BaseProvider
│       │   ├── claude_code.py      # ClaudeCodeProvider
│       │   ├── gemini.py           # GeminiProvider
│       │   ├── hermes.py           # HermesProvider
│       │   ├── local_git.py        # LocalGitProvider
│       │   ├── obsidian.py         # ObsidianProvider
│       │   └── opencode.py         # OpenCodeProvider
│       │   └── context/
│       │       ├── __init__.py
│       │       ├── git.py          # GitContextSource
│       │       ├── obsidian.py     # ObsidianContextSource
│       │       └── qmd.py           # QMDContextSource
│       │
│       └── utils/
│           └── limiter.py          # Rate limiting utilities
│
├── chroma_db/                   # ChromaDB storage (gitignored)
├── recall.db                    # SQLite database (gitignored)
├── recall.log                   # Log file (gitignored)
├── .env.local                  # Local configuration (gitignored)
├── .env.local.example          # Example configuration
├── pyproject.toml              # Project metadata, dependencies
├── README.md                    # User documentation
└── docs/                        # Technical documentation
    ├── ARCHITECTURE.md           # This file
    ├── CLI_USAGE.md              # CLI reference
    └── README.md                 # docs overview
```

---

## Integration Points

### Adding New Providers

To add a new AI platform provider:

1. Create new file: `src/recall/providers/<name>.py`
2. Implement `BaseProvider` interface:
   - `discover(date_range, **kwargs) -> List[str]`
   - `parse(source_id) -> Optional[ParsedSession]`
3. Register in `MultiSourceCorrelator.__init__()`:
   ```python
   self.providers = {
       ...,
       "new_provider": NewProvider(),
   }
   ```
4. Add to CLI platform list
5. Write tests

### Adding New Context Sources

To add a new context source:

1. Create new file: `src/recall/providers/context/<name>.py`
2. Implement `ContextSource` interface:
   - `source_type: str` property
   - `is_available() -> bool` (async)
   - `find_relevant_content(insights, session_context) -> List[ContextMatch]` (async)
3. Register in `create_context_manager()`:
   ```python
   if "new_source" in settings.context_sources:
       from recall.providers.context.new_source import NewContextSource
       manager.register_source(NewContextSource(settings))
   ```
4. Add to settings: `context_sources` list

### Custom DSPy Modules

To extend AI analysis:

1. Add signature in `src/recall/ai/signatures.py`
2. Create module in `src/recall/ai/modules.py`
3. Use in `MultiSourceCorrelator` as needed

---

## Best Practices

### For Users

1. **Start Small**: Begin with `recall extract --days 1` to test
2. **Use --tui**: Visual feedback during long operations
3. **Enable Context**: Use `--enhance-context` for richer insights
4. **Check DLQ**: Regularly run `recall dlq --retry`
5. **Backup**: Regularly backup `recall.db` and `chroma_db/`

### For Developers

1. **Thread Safety**: Always use locks for shared state
2. **Error Handling**: Use retry decorator for external calls
3. **Rate Limiting**: Always use `get_limiter()` for API calls
4. **Logging**: Use structured logging functions
5. **Testing**: Test with small datasets first

---

## Future Enhancements

Potential areas for improvement:

1. **Async Support**: Convert to async/await for better I/O handling
2. **Incremental Extraction**: Track last extraction time, only process new data
3. **More Providers**: Vibe, Cursor, GitHub Copilot, etc.
4. **Advanced Correlation**: Temporal clustering, anomaly detection
5. **Export Formats**: Markdown reports, Obsidian notes, etc.
6. **API Server**: REST/GraphQL interface for integration
7. **Scheduled Runs**: Cron-based automatic extraction
8. **Web UI**: Browser-based dashboard
9. **Advanced Search**: Full-text search, filters, faceting
10. **Collaboration**: Shared databases, team features

---

## Summary

Recall is a sophisticated system that:

1. **Extracts** from 5+ platforms with pluggable architecture
2. **Normalizes** to a rich, unified data model
3. **Analyzes** using DSPy for structured insights
4. **Enriches** with multi-source context
5. **Correlates** across time and platforms
6. **Persists** with resilience and recoverability
7. **Searches** semantically via embeddings
8. **Visualizes** via Rich TUI

The architecture emphasizes:
- **Modularity**: Pluggable providers and context sources
- **Resilience**: Rate limiting, retries, DLQ, dual-write safety
- **Performance**: Parallel processing, connection pooling, batching
- **Flexibility**: Configurable via environment variables and CLI
- **Observability**: Comprehensive logging and metrics

This combination makes Recall a powerful tool for understanding and correlating development work across disparate systems.
