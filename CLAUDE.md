# CLAUDE.md - Recall 🧠

## Project Context
Recall is a multi-platform session extraction and correlation tool using Python, DSPy, and SQLite.

## Architecture Decisions

### AI Analysis Pipeline
The analysis pipeline uses a layered approach:
1.  **Contextual Chunking**: `ContextualChunker` (src/recall/ai/chunking.py) splits large sessions.
2.  **DSPy Signatures**: `SessionTopicExtractor` (src/recall/ai/signatures.py) defines the LLM interface.
3.  **DSPy Modules**: `SessionAnalysisModule` (src/recall/ai/modules.py) orchestrates extraction and aggregation.
4.  **Persistence**: `PersistenceManager` (src/recall/db/manager.py) routes data to SQLite and ChromaDB.

## Development Guidelines

### Adding a New Analysis Type
To add a new session analysis metric (e.g., complexity, sentiment):

1.  **Update Signature**: Add the output field to `SessionTopicExtractor` in `src/recall/ai/signatures.py`.
    - Example: `complexity_score: int = dspy.OutputField(desc="...")`
2.  **Update Module**: Update `SessionAnalysisModule.forward` in `src/recall/ai/modules.py` to aggregate the new field from chunks.
3.  **Update Models**: Add the field to the `SessionAnalysis` Pydantic model in `src/recall/models.py`.
4.  **Update Persistence**:
    - Update `sqlite_store.py`: Add the column to `session_analysis` table and update `save_analysis`/`get_analysis`.
5.  **Update Orchestrator**: In `src/recall/core.py`, ensure `analyze_session_topics` result is mapped to the `SessionAnalysis` object.

### Verification Checklist
- [ ] DSPy signature has clear descriptions for new fields.
- [ ] Aggregation logic in the module handles empty or partial results from chunks.
- [ ] SQLite schema migration is handled (or DB is reset for development).
- [ ] TUI/CLI output is updated to display the new metric if applicable.
