# CLAUDE.md — AI Assistant Guide for TestRepository

## Project Overview

This is a **pure Python job scheduler library** with no external runtime dependencies (stdlib only). It supports interval, cron, and one-time scheduling strategies with thread-safe concurrent execution and job dependency management.

**Python requirement:** >= 3.11

---

## Repository Structure

```
TestRepository/
├── scheduler/              # Main library package
│   ├── __init__.py         # Public API exports
│   ├── scheduler.py        # Core scheduler engine (Scheduler class)
│   ├── job.py              # Job class, JobStatus enum, JobResult dataclass
│   ├── schedules.py        # Schedule types: IntervalSchedule, CronSchedule, OneTimeSchedule
│   └── cron_parser.py      # 5-field cron expression parser
├── tests/                  # Test suite (unittest)
│   ├── test_scheduler.py   # Scheduler integration tests
│   ├── test_job.py         # Job unit tests
│   ├── test_cron_parser.py # Cron parser tests
│   └── test_schedules.py   # Schedule type tests
├── examples/
│   └── example_usage.py    # Working examples for all scheduling strategies
├── requirements.txt        # No runtime deps; pip install pytest for dev
└── CLAUDE.md               # This file
```

---

## Architecture

### Core Classes

| Class | File | Responsibility |
|---|---|---|
| `Scheduler` | `scheduler.py` | Orchestrates all jobs; manages thread pool, dependency graph, scheduling loop |
| `Job` | `job.py` | Single schedulable unit; tracks state, history, retries, dependencies |
| `JobStatus` | `job.py` | Enum: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `EXPIRED` |
| `JobResult` | `job.py` | Dataclass recording a single execution attempt |
| `IntervalSchedule` | `schedules.py` | Fire every N seconds/minutes/hours/days |
| `CronSchedule` | `schedules.py` | Fire on a 5-field cron expression |
| `OneTimeSchedule` | `schedules.py` | Fire once at a specific `datetime` |
| `CronExpression` | `cron_parser.py` | Parse and evaluate 5-field cron strings |

### Public API

```python
from scheduler import (
    Scheduler,
    Job,
    IntervalSchedule,
    CronSchedule,
    OneTimeSchedule,
    CircularDependencyError,
    DuplicateJobError,
    JobNotFoundError,
)
```

All public symbols are re-exported from `scheduler/__init__.py`.

### Concurrency Model

- `Scheduler` runs a **background scheduling loop** in a daemon thread (configurable `tick_interval`, default 1 s).
- Jobs execute in a `ThreadPoolExecutor` (configurable `max_workers`, default 4).
- The job registry is protected by an `RLock`.
- `Job` state is managed with its own `RLock` for thread-safe status transitions.

### Dependency Graph

- Jobs declare dependencies via `dependencies: list[str]` (list of job names).
- `Scheduler.add_job()` validates for cycles using DFS before accepting the job.
- A job only runs when all its dependencies have `JobStatus.COMPLETED`.
- Raises `CircularDependencyError` on a cycle; `DuplicateJobError` on name collision.

---

## Key Conventions

### Code Style

- Pure Python stdlib — **never introduce external runtime dependencies**.
- Use `dataclasses` for value objects (`JobResult`).
- Use `abc.ABC` / `@abstractmethod` for schedule base class.
- Thread safety: always acquire the relevant `RLock` before reading/writing shared mutable state.
- Exceptions are defined at the module level and re-exported from `__init__.py`.

### Schedule Implementations

All schedules inherit from the abstract `Schedule` base class (`schedules.py`) and must implement:
- `next_run(after: datetime) -> datetime | None` — return the next fire time or `None` if exhausted.
- `description() -> str` — human-readable string.

### Cron Parser

- Supports standard 5-field format: `minute hour dom month dow`
- Accepts wildcards (`*`), ranges (`1-5`), steps (`*/5`, `1-5/2`), and lists (`1,3,5`).
- Month aliases: `jan`–`dec`; weekday aliases: `mon`–`sun`.
- Day-of-month and day-of-week use **OR semantics** (Vixie cron behavior) when both are restricted.
- `CronExpression.next_after(dt)` searches up to 4 years before raising `StopIteration`.

### Error Handling

- `Job.run()` **never raises** — all exceptions from the user callable are caught and stored in `JobResult`.
- `Scheduler` methods raise typed exceptions (`CircularDependencyError`, `DuplicateJobError`, `JobNotFoundError`) for invalid operations.

---

## Development Workflow

### Running Tests

```bash
# Using unittest (no install required)
python -m unittest discover -s tests

# Using pytest (install once)
pip install pytest
pytest tests/
```

All 95 tests should pass. Typical run time is ~3 s.

### Adding a New Schedule Type

1. Add a class to `scheduler/schedules.py` inheriting from `Schedule`.
2. Implement `next_run()` and `description()`.
3. Export the new class in `scheduler/__init__.py`.
4. Add tests in `tests/test_schedules.py`.

### Adding a New Job Feature

1. Modify `scheduler/job.py` (state, status transitions, `is_ready()` logic).
2. If the `Scheduler` loop needs to handle the feature, update `scheduler/scheduler.py`.
3. Add or update tests in `tests/test_job.py` and/or `tests/test_scheduler.py`.

### Modifying the Cron Parser

- All parsing lives in `scheduler/cron_parser.py` (`CronExpression` class).
- Edge cases to keep in mind: leap years, month-end rollover, weekday-vs-dom OR semantics.
- Tests are in `tests/test_cron_parser.py`.

---

## Testing Patterns

- Tests use Python's built-in `unittest.TestCase` — no pytest-specific features.
- Helper factory functions (e.g., `make_job()`, `make_scheduler()`) are defined at module level in each test file.
- Integration tests start the scheduler with a short `tick_interval` and `time.sleep()` to let jobs execute, then assert on state.
- Avoid `time.sleep()` in unit tests for `Job` and schedule classes — those are fully synchronous.

---

## What NOT to Do

- Do not add external runtime dependencies — the library is stdlib-only by design.
- Do not remove the `RLock` guards in `Job` or `Scheduler` — the library is designed for multi-threaded use.
- Do not change `Job.run()` to raise exceptions — callers rely on it being safe to call from a thread pool.
- Do not break the `scheduler/__init__.py` public API without updating all exports.
