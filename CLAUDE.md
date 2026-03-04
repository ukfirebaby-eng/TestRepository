# CLAUDE.md — AI Assistant Guide for TestRepository

## Project Overview

This is a **pure Python job scheduler library** with zero external runtime dependencies. It supports interval-based, cron-based, and one-time scheduling with job dependencies, retry logic, and concurrent execution via thread pools.

- **Language**: Python 3.11+
- **Dependencies**: Python standard library only (no `pip install` needed at runtime)
- **Dev dependency**: `pytest` (optional; `unittest` also works)

---

## Repository Structure

```
TestRepository/
├── scheduler/              # Main library package
│   ├── __init__.py         # Public API — all user-facing exports
│   ├── scheduler.py        # Scheduler class (orchestrator)
│   ├── job.py              # Job class, JobStatus enum, JobResult dataclass
│   ├── cron_parser.py      # Cron expression parser (CronExpression, CronParseError)
│   └── schedules.py        # Schedule strategies (Interval, Cron, OneTime)
├── tests/                  # Test suite (unittest)
│   ├── test_scheduler.py   # Integration tests for Scheduler
│   ├── test_job.py         # Unit tests for Job
│   ├── test_cron_parser.py # Unit tests for cron parsing
│   └── test_schedules.py   # Unit tests for schedule types
├── examples/
│   └── example_usage.py    # Runnable demo of all major features
└── requirements.txt        # Runtime: none; Dev: pytest
```

---

## Architecture

### Public API (`scheduler/__init__.py`)

All 13 public exports:

| Symbol | Kind | Description |
|---|---|---|
| `Scheduler` | class | Main orchestrator |
| `Job` | class | A schedulable unit of work |
| `JobStatus` | enum | `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `EXPIRED` |
| `JobResult` | dataclass | Immutable record of one execution attempt |
| `Schedule` | ABC | Base class for all schedule strategies |
| `IntervalSchedule` | class | Repeat every N seconds/minutes/hours/days |
| `CronSchedule` | class | Fire on a cron expression |
| `OneTimeSchedule` | class | Fire once at a specific `datetime` |
| `CronExpression` | class | Low-level cron parser (rarely used directly) |
| `CircularDependencyError` | exception | Cycle in job dependency graph |
| `CronParseError` | exception | Invalid cron expression |
| `DuplicateJobError` | exception | Job name already registered |
| `JobNotFoundError` | exception | Referenced job not found |

### Module Responsibilities

- **`scheduler.py`**: Manages the job registry, runs the scheduling loop in a background thread (or blocking), dispatches jobs via `ThreadPoolExecutor`, validates dependency DAGs (DFS cycle detection), handles retries with exponential backoff.
- **`job.py`**: Encapsulates the callable, schedule, retry config, execution history, and thread-safe state transitions. `is_ready(now, completed_names)` is the gate for execution.
- **`cron_parser.py`**: Parses 5-field cron expressions (`min hour day month weekday`). Supports `*`, `*/n`, `n-m`, lists, and month/weekday name aliases. Implements Vixie cron OR semantics for day fields.
- **`schedules.py`**: Three concrete `Schedule` implementations with a uniform `next_run(after: datetime) -> datetime | None` interface.

---

## Development Workflows

### Running Tests

```bash
# Using unittest (no install needed)
python -m unittest discover tests

# Using pytest
pytest

# Run a specific test file
python -m unittest tests.test_scheduler
pytest tests/test_scheduler.py

# Run a specific test case
python -m unittest tests.test_cron_parser.TestCronExpression
pytest tests/test_cron_parser.py::TestCronExpression
```

### Running the Example

```bash
python examples/example_usage.py
```

### Importing the Library (from repo root)

```python
from scheduler import Scheduler, Job, IntervalSchedule, CronSchedule, OneTimeSchedule
```

No installation step is required — run from the repo root.

---

## Key Conventions

### Naming

- **Modules**: `snake_case`
- **Classes**: `PascalCase`
- **Methods / variables**: `snake_case`
- **Private methods/attributes**: single leading underscore (e.g., `_scheduling_loop`, `_lock`)

### Design Patterns in Use

1. **Abstract Base Class** — `Schedule` is an ABC; all schedule strategies inherit and implement `next_run()` and `description()`.
2. **Enum** — `JobStatus` models finite job states; never use bare strings for status.
3. **Dataclass** — `JobResult` is a frozen/immutable record; do not mutate it.
4. **Thread safety** — Both `Scheduler` and `Job` use `threading.RLock`. Always acquire the lock before reading or writing shared mutable state.
5. **Dependency injection** — `Scheduler` accepts a `clock` callable (default `datetime.now`) for deterministic testing. Use this in all new tests that care about time.
6. **No-raise execution** — `job.run()` catches all exceptions internally and stores them in `JobResult`. Callers should inspect the result, not catch exceptions from `run()`.

### Error Handling

- Raise domain-specific exceptions (`DuplicateJobError`, `JobNotFoundError`, `CronParseError`, `CircularDependencyError`) at API boundaries.
- Never let job exceptions propagate out of `Job.run()`; capture them in `JobResult`.
- Scheduler internal errors (e.g., thread pool issues) should be logged, not silently swallowed.

### Testing Conventions

- Test framework: **unittest** (`TestCase` subclasses).
- Group related tests in named `TestCase` classes (e.g., `TestSchedulerJobRegistration`).
- Use the `clock` injection point on `Scheduler` to control time in tests — avoid `time.sleep` where possible.
- Helper factories like `_make_counter_func()` are fine for shared test fixtures; keep them module-private.
- Test files mirror source modules: `scheduler/job.py` → `tests/test_job.py`.

---

## Scheduler Configuration

```python
Scheduler(
    max_workers=4,       # ThreadPoolExecutor pool size
    tick_interval=1.0,   # Seconds between scheduling loop ticks
    clock=datetime.now,  # Injectable time source (use for testing)
)
```

## Job Configuration

```python
Job(
    name="my_job",               # Unique string identifier
    func=my_callable,            # The function to run
    schedule=IntervalSchedule(seconds=30),
    args=(),                     # Positional args passed to func
    kwargs={},                   # Keyword args passed to func
    max_retries=0,               # 0 = no retries
    retry_delay=60.0,            # Seconds before retry
    dependencies=[],             # List of job names that must complete first
)
```

## Schedule Types

```python
# Repeat every N units
IntervalSchedule(seconds=30)
IntervalSchedule(minutes=5, hours=1)   # combined: 1h 5m

# Standard 5-field cron
CronSchedule("*/15 9-17 * * mon-fri") # Every 15 min, 9am-5pm, weekdays

# Fire once
OneTimeSchedule(datetime(2026, 6, 1, 12, 0, 0))
```

---

## Adding New Features

### New Schedule Type

1. Add a new class to `scheduler/schedules.py` that extends `Schedule`.
2. Implement `next_run(after: datetime) -> datetime | None` and `description() -> str`.
3. Export the new class from `scheduler/__init__.py`.
4. Add tests to `tests/test_schedules.py`.

### New Scheduler Capability

1. Modify `scheduler/scheduler.py`.
2. If adding public API, export from `scheduler/__init__.py`.
3. Add integration tests to `tests/test_scheduler.py`.

### Extending Job Behavior

1. Modify `scheduler/job.py`.
2. Ensure any new state is protected by `self._lock`.
3. Add unit tests to `tests/test_job.py`.

---

## Important Constraints

- **Python 3.11+ required** — uses `datetime` features and type annotations consistent with 3.11+.
- **No external dependencies** — do not add third-party packages to the runtime code path. Dev-only tools (pytest, mypy, black) are fine in `requirements.txt` with a comment.
- **Thread safety is non-negotiable** — any shared mutable state on `Job` or `Scheduler` must be guarded by the existing `RLock`.
- **Jobs must not raise** — `Job.run()` swallows exceptions and stores them in `JobResult.error`. This contract must be preserved.
- **Cron day-of-week/day-of-month semantics** — the parser uses Vixie cron OR logic (if both fields are restricted, either match fires). Do not change this without updating tests.

---

## Git Workflow

- Active development branch: `claude/add-claude-documentation-Cevpk`
- Remote: configured via local proxy
- Commit messages should be descriptive and reference the change area (e.g., `"scheduler: add graceful shutdown timeout option"`)
- Do not commit `__pycache__/` or `.pyc` files (add to `.gitignore` if not already excluded)
