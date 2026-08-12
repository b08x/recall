# Design Decisions & Rationale

Extracted from inline comments (`# NOTE:`, `# WHY:`, `# HACK:`, `# TODO:`) and design documents via graphify. Modality reflects extraction confidence.

## Dual-Write Resilience

**Extracted from**: `src/recall/db/manager.py:54-55` *(EXTRACTED)*
**Decision**: SQLite data is committed **before** vector indexing; vector failures are recorded in DLQ without raising exceptions
**Rationale**: Ensures data integrity — if vector indexing fails, the relational data is already persisted and can be reconciled later
**Trade-offs**: May leave orphaned vector data if SQLite commit succeeds but vector write fails; requires reconciliation logic to clean up

## Contextual Chunker Design

**Extracted from**: `src/recall/ai/chunking.py:32-44` *(EXTRACTED)*
**Decision**: Split sessions based on 6000-char length limit and 30-minute time gaps; prefer splitting on user messages
**Rationale**: Balances chunk size for LLM context windows with semantic coherence; temporal boundaries help preserve conversation flow
**Trade-offs**: Large single user messages (>6000 chars) are truncated rather than split; may produce suboptimal chunks for code-heavy sessions

## DSPy Availability Fallback

**Extracted from**: `src/recall/ai/modules.py:348-352` *(EXTRACTED)*
**Decision**: When `dspy` is unavailable, provide no-op classes that maintain interface compatibility
**Rationale**: Allows the system to run in analysis-only mode without AI-powered features; graceful degradation
**Trade-offs**: Without DSPy, insight extraction degrades to keyword matching without semantic understanding

## Named Rate Limiters

**Extracted from**: `src/recall/core.py:48-49` *(EXTRACTED)*
**Decision**: Use per-platform rate limiters (`"gemini"`, `"hermes"`, `"claude"`) rather than a single global limiter
**Rationale**: Platforms have different API rate limits and priorities; per-platform control prevents one platform from blocking others
**Trade-offs**: More complex configuration; requires mapping each platform to a named limiter

## SQLite WAL Mode

**Extracted from**: `src/recall/db/sqlite_store.py:26` *(EXTRACTED)*
**Decision**: Enable `PRAGMA journal_mode=WAL` for concurrent read/write access
**Rationale**: WAL mode allows multiple readers while a writer is active, improving concurrency for parallel extraction
**Trade-offs**: WAL files may consume additional disk space; requires careful connection management

## Dual-Embedding Support

**Extracted from**: `src/recall/db/vector_store.py:34-91` *(EXTRACTED)*
**Decision**: Support both `DSPyEmbeddingFunction` (multi-provider via LiteLLM) and `OllamaEmbeddingFunction` (local models)
**Rationale**: Flexibility for different deployment scenarios — local models for privacy-sensitive environments, DSPy for multi-provider convenience
**Trade-offs**: Two embedding implementations require maintenance; dimension compatibility checking needed when switching

## Context Enhancement Timeout

**Extracted from**: `src/recall/config.py:63` *(EXTRACTED)*
**Decision**: 30-second timeout for context enhancement operations
**Rationale**: Context sources (Obsidian, Git) may be slow; timeout prevents indefinite hanging
**Trade-offs**: Long-running context queries may be truncated; may miss relevant matches

## DLQ as Persistent Queue

**Extracted from**: `src/recall/db/sqlite_store.py:138-145` *(EXTRACTED)*
**Decision**: Failed sessions are persisted in a `dlq` table with retry count rather than in-memory
**Rationale**: Survives process restarts; enables retry logic across multiple runs
**Trade-offs**: Requires periodic cleanup of old DLQ items; adds schema complexity

## Thread-Local SQLite Connections

**Extracted from**: `src/recall/db/sqlite_store.py:18` *(EXTRACTED)*
**Decision**: Use `threading.local()` for SQLite connections to support parallel processing
**Rationale**: Each thread gets its own connection, avoiding serialization bottlenecks
**Trade-offs**: Connections are not shared across threads; must be closed per-thread; may exhaust file descriptors under high concurrency

## Pydantic Settings with SecretStr

**Extracted from**: `src/recall/config.py:38-41` *(EXTRACTED)*
**Decision**: Use `SecretStr` for API keys to prevent accidental logging/serialization
**Rationale**: Security — API keys should not appear in logs or error messages
**Trade-offs**: `SecretStr` adds minor overhead; requires `.get_secret_value()` for actual use

## OpenRouter as Default DSPy Provider

**Extracted from**: `src/recall/config.py:17` *(EXTRACTED)*
**Decision**: Default `dspy_provider` to `"openrouter"` for broad model access
**Rationale**: OpenRouter provides access to multiple LLM providers (OpenAI, Anthropic, Gemini) through a single API
**Trade-offs**: Vendor lock-in to OpenRouter; users may prefer direct provider access for cost/control reasons

## TUI Dashboard

**Extracted from**: `src/recall/cli.py:33` *(EXTRACTED)*
**Decision**: Rich-based TUI for interactive monitoring during long operations
**Rationale**: Long-running extractions (hours for many sessions) benefit from visual progress indication
**Trade-offs**: Adds `rich` as a dependency; terminal compatibility issues on some systems
