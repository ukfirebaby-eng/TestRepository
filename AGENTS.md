# Repository Guidelines

## Working Rules

- Do not make code changes until you have high confidence in the required behavior. Ask follow-up questions when requirements are ambiguous or risky.
- Preserve existing user work. Do not revert unrelated changes or run destructive git commands unless explicitly requested.
- Keep the "Applied Learning" list in `CLAUDE.md` updated only for repeated failures, re-explained preferences, or platform/tool workarounds. Use one bullet under 15 words.
- Treat pinned dependency versions documented in `CLAUDE.md` as project decisions, even if `requirements.txt` is less specific.

## Project Shape

- Main Diamond Miner app: `api.py`, launched through `run.py`.
- UI: `static/index.html`, a single-file vanilla JS frontend with CDN dependencies.
- Core backend modules live in `core/`.
- Tests live in `tests/`.
- `main.py`, `data_fetcher.py`, and `sentiment_model.py` define a separate TikTok sentiment FastAPI sample. Do not assume they are the Diamond Miner entry point.

## Running

```bash
python run.py
```

This starts Uvicorn on `http://localhost:8000` and creates `vaults`, `static`, and `temp_uploads` as needed.

Relevant environment variables:

- `OPENAI_API_KEY`
- `OPENROUTER_API_KEY`
- `LLM_PROVIDER`
- `FAST_MODEL`
- `SMART_MODEL`
- `VAULT_PATH`
- `DIAMOND_MINER_PORT` defaults to `8000`
- `DIAMOND_MINER_STOP_STALE_SERVER=1` stops Python processes bound to the configured port
- `DIAMOND_MINER_FORCE_STOP_PORT_PROCESS=1` force-stops an uninspectable process on the configured port

## Testing

```bash
pytest tests/
pytest tests/test_vault_narrative.py
pytest tests/test_vault_executive.py::TestGetExecutiveSummary::test_returns_none_when_no_cache
python -m pytest -m evaluation -q
```

Tests are expected to mock LLM calls and use isolated temporary data. Prefer focused tests first, then broader test runs when the change is complete.
Use the `evaluation` marker as the deterministic analytical quality gate for fixture baselines.

## CI / Quality Gates

The deterministic CI evaluation gate is:

```bash
python -m pytest -m evaluation -q
```

Live model evaluation is intentionally separate from CI. Run it only with an explicit opt-in:

```bash
set DIAMOND_MINER_LIVE_EVALUATION=1
python -m pytest -m live_evaluation -q
```

Live evaluation uses the configured LLM provider and can vary with provider/model behaviour.

## Architecture Notes

- `api.py` owns the FastAPI routes, static UI mount, shared local vault, job store, and SSE report generation flows.
- `core/vault.py` implements `HybridVault`, combining per-tenant SQLite files with ChromaDB storage under `vaults/{tenant_id}/`.
- `core/orchestrator.py` coordinates document ingestion and analysis using the agent classes.
- `core/agents.py` contains extraction, analysis, drafting, critique, and coverage-check agents.
- `core/simulator.py` contains blast-radius, black-swan, and Monte Carlo risk simulations.

## Implementation Practices

- Keep API paths and frontend calls aligned; the frontend uses relative `/api/v1/...` paths.
- Guard long-running report generation against duplicate in-flight work, matching existing `_active_*` set patterns.
- Keep report cache semantics consistent: GET returns cached status, POST generates and caches, DELETE is idempotent unless the document is unknown.
- Avoid live LLM or external API calls in tests.
- Use `rg` for search and prefer focused edits over broad rewrites.
