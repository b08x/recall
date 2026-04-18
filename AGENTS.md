## Logging Implementation Details

The updated logging module (`src/recall/logging.py`) now supports structured step timing via a context manager and emits key metrics:

```python
with step("extract_all", f"days={days}, platforms={platforms}, analyze={analyze}"):
    ...
with step(f"extract_platform:{platform}"):
    ...
with step(f"process_session:{session.id[:8]}"):
    ...
with step("analyze_session_topics", ...):
    ...
with step("analyze_session_insights", ...):
    ...
with step("persist_session:..."):
    ...
with step("build_timeline"):
    ...
with step("correlate_with_dspy", ...):
    ...
```

Each `step` context emits `STEP_START` and `STEP_COMPLETE` entries with elapsed duration. Metrics are also emitted via `log_metric()` for aggregate monitoring (e.g., `total_sessions`, `dspy_available`, `topics_extracted`, `timeline_total`).

Use `recall.log` (or `recall.logs/recall.log`) for traceability across pipeline stages to debug extraction, correlation, or analysis bottlenecks.

### Key Metrics Added
- `extract_all_started`: Marks extraction pipeline start
- `target_platforms`: Number of platforms being processed
- `platform_iteration`: Current platform being extracted
- `sessions_per_platform`: Session count per platform
- `total_sessions`: Aggregate session count across all platforms