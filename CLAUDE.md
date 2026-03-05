# CLAUDE.md — AI Assistant Guide for Simple Job Scheduler

This file provides context for AI assistants (Claude Code and others) working on this codebase.

---

## Project Overview

**Simple Job Scheduler** is a pure Python library for scheduling and executing jobs with support for:
- Interval-based, cron-expression, and one-time schedules
- Job dependency graphs (DAG) with circular dependency detection
- Concurrent execution via `ThreadPoolExecutor`
- Retry logic with exponential backoff
- Thread-safe state management

**Language:** Python 3.11+
**Dependencies:** None (stdlib only). `pytest` is the only dev dependency.

---

## Repository Structure

```
/
├── scheduler/              # Main package
│   ├── __init__.py         # Public API exports
│   ├── scheduler.py        # Core Scheduler engine
│   ├── job.py              # Job class, JobStatus enum, JobResult dataclass
│   ├── schedules.py        # IntervalSchedule, CronSchedule, OneTimeSchedule
│   └── cron_parser.py      # 5-field cron expression parser
├── tests/
│   ├── test_scheduler.py   # Scheduler integration tests
│   ├── test_job.py         # Job unit tests
│   ├── test_cron_parser.py # Cron parser unit tests
│   └── test_schedules.py   # Schedule types unit tests
├── examples/
│   └── example_usage.py    # Runnable demo of all features
└── requirements.txt        # Python >= 3.11, no runtime deps
```

---

## Key Modules & Architecture

### `scheduler/scheduler.py` — `Scheduler`
The central engine. Key responsibilities:
- Maintains a job registry (`dict[str, Job]`)
- Validates and stores a dependency graph (adjacency list)
- Runs a background scheduling loop (`threading.Thread` + `tick_interval`)
- Dispatches ready jobs to a `ThreadPoolExecutor`
- Detects circular dependencies via DFS before adding any job

Constructor parameters:
```python
Scheduler(max_workers=4, tick_interval=1.0, clock=datetime.now)
```
- `clock` is injectable for testing (pass a mock returning controlled datetimes)

### `scheduler/job.py` — `Job`, `JobStatus`, `JobResult`
- `Job` wraps a callable with its schedule, retry config, and execution state
- `JobStatus` enum: `PENDING | RUNNING | COMPLETED | FAILED | EXPIRED`
- `JobResult` is an immutable dataclass recording each execution outcome
- All state mutations are protected by `threading.RLock`

### `scheduler/schedules.py` — Schedule Types
All subclass abstract `Schedule` and implement `next_after(dt: datetime) -> datetime`:

| Class | Description |
|---|---|
| `IntervalSchedule` | Fires every N seconds/minutes/hours/days |
| `CronSchedule` | Fires per 5-field cron expression |
| `OneTimeSchedule` | Fires once at a specific `datetime` |

### `scheduler/cron_parser.py` — `CronExpression`
Parses 5-field cron strings: `"minute hour day month weekday"`.
- Supports: `*`, `*/n` (step), `n-m` (range), `n,m` (list), month/weekday aliases
- Uses Vixie cron semantics: day-of-month and day-of-week are OR'd when both are non-wildcard
- `next_after(dt)` searches up to 4 years ahead before raising `CronParseError`

### `scheduler/__init__.py` — Public API
Everything a consumer needs is exported here:
```python
from scheduler import (
    Scheduler, Job, JobStatus, JobResult,
    Schedule, IntervalSchedule, CronSchedule, OneTimeSchedule,
    CircularDependencyError, CronParseError, DuplicateJobError, JobNotFoundError,
    CronExpression,   # low-level, rarely needed directly
)
```

---

## Development Workflow

### Running Tests
```bash
# Install dev dependency (first time)
pip install pytest

# Run all tests
pytest

# Run a specific test file
pytest tests/test_scheduler.py

# Run with verbose output
pytest -v

# Run a single test by name
pytest -k "test_circular_dependency"
```

There is no `Makefile`, `tox.ini`, or CI pipeline configured yet. Tests are run directly with `pytest`.

### Running the Example
```bash
python examples/example_usage.py
```
This runs a live demo with interval, cron, one-time, and dependency-chained jobs for ~15 seconds.

---

## Coding Conventions

### Style
- **No formatter or linter is configured.** Follow PEP 8 manually.
- Type hints are used throughout — maintain them when adding code.
- Docstrings use Google-style format (Args/Returns/Raises sections).

### Thread Safety
- Any state shared between the scheduler loop and job threads must be accessed under a lock.
- `Job` uses `threading.RLock` for all mutable state.
- `Scheduler` uses its own `threading.RLock` for the job registry and dependency graph.
- Never acquire a `Job` lock while holding the `Scheduler` lock (deadlock risk).

### Error Handling
- Domain exceptions live in `scheduler/__init__.py` exports and are raised by the library; do not swallow them silently.
- Key exceptions: `CircularDependencyError`, `DuplicateJobError`, `JobNotFoundError`, `CronParseError`.

### Adding a New Schedule Type
1. Subclass `Schedule` in `scheduler/schedules.py`
2. Implement `next_after(self, dt: datetime) -> datetime`
3. Export it from `scheduler/__init__.py`
4. Add tests in `tests/test_schedules.py`

### Adding a New Feature to `Scheduler`
- Keep the public API surface in `__init__.py` exports consistent
- Add corresponding tests in `tests/test_scheduler.py`
- Use the injectable `clock` parameter in tests to avoid real-time sleeps

---

## Testing Conventions

- Tests use `unittest.TestCase` style classes with `pytest` as the runner.
- Time-sensitive tests inject a mock `clock` function into `Scheduler` instead of sleeping.
- Each test class focuses on one module or behavior area (see existing test file structure).
- Use `threading.Event` and short `time.sleep` durations (e.g., 0.1–0.5 s) for integration tests that start the scheduler loop.
- Keep test jobs fast (use `lambda` or simple functions returning immediately).

---

## Common Pitfalls

- **Circular imports:** `scheduler/scheduler.py` imports from `job.py` and `schedules.py`. `job.py` imports from `schedules.py`. Do not import `scheduler.py` from `job.py` or `schedules.py`.
- **Cron day logic:** Day-of-month and day-of-week use OR semantics when both are specified (not AND). This matches Vixie cron behavior.
- **OneTimeSchedule after firing:** After the scheduled time passes, `next_after` returns `None` (job expires). Account for this in tests.
- **RLock re-entrancy:** `Job` uses `RLock` specifically to allow the same thread to re-acquire it (e.g., when `run()` calls internal helpers). Do not replace with `Lock`.

---

## Not Yet Configured (Future Work)

- No CI/CD pipeline (GitHub Actions, etc.)
- No linter/formatter config (flake8, black, mypy)
- No `pyproject.toml` or `setup.py` (not installable as a package yet)
- No Docker environment
- No changelog or versioning
