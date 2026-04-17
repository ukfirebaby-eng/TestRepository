"""
String constants for all lat.md/ files written by `lat init`.
"""

ARCHITECTURE_MD = """\
# Architecture
<!-- file: lat.md/architecture.md -->

This file describes the structural components of the job scheduler engine.

## Scheduler Engine
<!-- id: scheduler-engine -->
<!-- require-code-mention: true -->

`Scheduler` is the central orchestrator in [[public-api]]. It owns the job
registry, the thread pool, and the scheduling loop.

Key fields:
- `_jobs: dict[str, Job]` — the live job registry
- `_executor: ThreadPoolExecutor` — see [[thread-pool-design]]
- `_lock: RLock` — serialises all registry mutations
- `_resolver: GenesisResolver | None` — optional intelligent recovery; see [[genesis-resolver]]
- `_clock` — injectable clock function; see [[injectable-clock]]

File reference: [[scheduler/scheduler.py#Scheduler]]

## Scheduling Loop
<!-- id: scheduler-loop -->
<!-- require-code-mention: true -->

`Scheduler._scheduling_loop()` runs in a daemon thread (or the calling thread
for `run_blocking()`). Each tick:

1. Collects names of all completed jobs via `_completed_job_names()`.
2. Drains any done futures, calling `_handle_result()` for each.
3. Iterates the registry and submits every job where `job.is_ready()` returns
   `True` (see [[job-readiness]]).
4. Sleeps for the remainder of `tick_interval`, using `stop_event.wait()` so
   it wakes immediately on `Scheduler.stop()`.

File reference: [[scheduler/scheduler.py#_scheduling_loop]]

## Result Handling
<!-- id: result-handling -->
<!-- require-code-mention: true -->

`Scheduler._handle_result(job, result)` is called while holding `_lock`.

**Success path:** calls `job.mark_completed()`, then `job.compute_next_run()`.
If `compute_next_run()` returns `None` the job has expired (one-time schedule).

**Failure path (resolver present):** delegates to [[genesis-resolver]].
`RecoveryAction` values map to:
- `RETRY_IMMEDIATE` / `RETRY_BACKOFF` / `SURGICAL_RETRY` → `job.schedule_retry(retry_at)`
- `SKIP` / `ESCALATE` → `job.mark_failed()`; still reschedules for next natural
  tick if the schedule allows.

**Failure path (no resolver):** default retry logic — if
`retry_count < max_retries`, calls `job.schedule_retry()`; otherwise
`job.mark_failed()`.

See also [[job-retry-logic]].

## Dependency Graph
<!-- id: dependency-graph -->
<!-- require-code-mention: true -->

When `add_job()` is called, `_check_for_cycle()` runs a DFS over the
registered job graph using WHITE / GRAY / BLACK node colouring:

- **WHITE** — unvisited
- **GRAY** — on the current DFS stack (back-edge → cycle)
- **BLACK** — fully explored (safe)

A `CircularDependencyError` is raised with the cycle path if a back-edge is
found. The job is removed from the registry before the error propagates, so
the registry stays consistent.

See [[circular-dependency-error]] for the error types, and [[job-readiness]]
for how dependencies affect execution.

## Error Types
<!-- id: circular-dependency-error -->

Three validation errors are raised by `Scheduler.add_job()`:

| Exception | When |
|-----------|------|
| `CircularDependencyError(ValueError)` | Adding a job creates a cycle |
| `DuplicateJobError(ValueError)` | A job with the same name already exists |
| `JobNotFoundError(KeyError)` | A dependency name refers to an unregistered job |

All three are exported from [[public-api]].
"""

CONCEPTS_MD = """\
# Concepts
<!-- file: lat.md/concepts.md -->

Core domain concepts for the job scheduler library.

## Job Model
<!-- id: job-model -->
<!-- require-code-mention: true -->

`Job` is the schedulable unit of work. It is thread-safe: all mutable state
is guarded by an internal `RLock`.

Important fields:
- `name: str` — unique identity within a `Scheduler`
- `func: Callable` — the work to execute
- `schedule: Schedule` — controls when the job fires; see [[schedule-types]]
- `dependencies: list[str]` — names of jobs that must complete first; see [[dependency-graph]]
- `max_retries / retry_delay_seconds` — retry budget; see [[job-retry-logic]]
- `status: JobStatus` — current state; see [[job-status]]
- `history: list[JobResult]` — immutable execution records

File reference: [[scheduler/job.py#Job]]

## Job Status
<!-- id: job-status -->
<!-- require-code-mention: true -->

`JobStatus` is a 5-value enum:

| Value | Meaning |
|-------|---------|
| `PENDING` | Waiting for next scheduled time or dependencies to complete |
| `RUNNING` | Currently executing in a thread-pool worker |
| `COMPLETED` | Last execution returned without exception |
| `FAILED` | Last execution raised an exception and retries are exhausted |
| `EXPIRED` | One-time job that has already fired (see [[schedule-types]]) |

See [[job-lifecycle]] for the state machine.

File reference: [[scheduler/job.py#JobStatus]]

## Job Lifecycle
<!-- id: job-lifecycle -->

```
PENDING ──► RUNNING ──► COMPLETED ──► PENDING  (rescheduled)
                │                 └──► EXPIRED   (one-time)
                └──► FAILED  ◄──── (retries exhausted)
                      │
                      └──► PENDING  (retry scheduled, see [[job-retry-logic]])
```

The `Scheduler` drives all transitions. `Job` itself only exposes
`mark_completed()`, `mark_failed()`, and `schedule_retry()` — the decision of
*which* to call lives in [[result-handling]].

## Job Readiness
<!-- id: job-readiness -->
<!-- require-code-mention: true -->

`Job.is_ready(now, completed_names)` returns `True` when all three hold:

1. `status == PENDING`
2. `next_run` is set and `<= now`
3. Every name in `dependencies` is in `completed_names`

`completed_names` is the set returned by `Scheduler._completed_job_names()`,
which includes jobs with status `COMPLETED` or `EXPIRED`.

File reference: [[scheduler/job.py#is_ready]]

## Job Retry Logic
<!-- id: job-retry-logic -->
<!-- require-code-mention: true -->

`Job.schedule_retry(retry_at)` increments `retry_count`, sets `next_run =
retry_at`, and resets `status` to `PENDING`.

The decision to retry (and at what time) is made in [[result-handling]]:

- Without a resolver: retry if `retry_count < max_retries`; otherwise fail.
- With a [[genesis-resolver]]: the resolver's `RecoveryAction` overrides this.

File reference: [[scheduler/job.py#schedule_retry]]
"""

API_MD = """\
# API Reference
<!-- file: lat.md/api.md -->

Public API surface of the scheduler library.

## Schedule Types
<!-- id: schedule-types -->
<!-- require-code-mention: true -->

Abstract base: `Schedule` with two abstract methods:
- `next_run(after: datetime) -> datetime | None`
- `description() -> str`

Concrete implementations:

| Class | Behaviour |
|-------|-----------|
| `IntervalSchedule(seconds, minutes, hours, days)` | Fires repeatedly at a fixed delta from the last run. Never drifts: each `next_run()` is `after + interval`. |
| `CronSchedule(expression)` | Fires per a 5-field cron expression; see [[cron-expression]]. |
| `OneTimeSchedule(run_at)` | Fires exactly once; returns `None` after triggering. Sets job status to `EXPIRED`. |

`CronParseError` is re-exported from `scheduler.schedules` for convenience.

File reference: [[scheduler/schedules.py#Schedule]]

## Cron Expression
<!-- id: cron-expression -->
<!-- require-code-mention: true -->

`CronExpression` parses and evaluates 5-field cron strings:

```
minute  hour  day  month  weekday
```

Supported syntax per field:
- `*` — every value
- `n` — exact value
- `n-m` — inclusive range
- `*/n` — step from min
- `n-m/n` — step within range
- `n,m,...` — list of values/ranges
- Month aliases: `jan`–`dec`
- Weekday aliases: `sun`–`sat`

Day-of-month and day-of-week use **OR semantics** when both are restricted —
see [[cron-or-semantics]].

Raises `CronParseError(ValueError)` for invalid expressions.

File reference: [[scheduler/cron_parser.py#CronExpression]]

## Public API
<!-- id: public-api -->

All names exported from `scheduler/__init__.py`:

```python
# Core
Scheduler, Job, JobStatus, JobResult

# Schedules
Schedule, IntervalSchedule, CronSchedule, OneTimeSchedule

# Errors
CircularDependencyError, CronParseError, DuplicateJobError, JobNotFoundError

# Low-level cron
CronExpression

# Genesis Resolver components
GenesisResolver, ErrorClassifier, ErrorCategory,
ViolationDetector, ViolationType, Violation,
RecoveryAction, ResolutionResult
```

See [[scheduler-engine]], [[job-model]], [[schedule-types]], [[genesis-resolver]].

## Injectable Clock
<!-- id: injectable-clock -->
<!-- require-code-mention: true -->

`Scheduler.__init__` accepts a `clock: Callable[[], datetime]` parameter.
When omitted it defaults to `datetime.now`. Injecting a custom clock enables
deterministic tests without real-time sleeping.

The clock is called at the start of every scheduling loop tick (to get
`tick_start`) and also by `initialize_next_run()` when a job is first
registered.

File reference: [[scheduler/scheduler.py#Scheduler]]
"""

DECISIONS_MD = """\
# Design Decisions
<!-- file: lat.md/decisions.md -->

Rationale behind key architectural and implementation choices.

## Zero External Dependencies
<!-- id: zero-deps -->

The library uses Python 3.11+ stdlib only (`threading`, `concurrent.futures`,
`dataclasses`, `enum`, `datetime`, `logging`). This keeps the install footprint
to zero and makes the library embeddable in any Python project without
dependency conflicts.

Development tooling (pytest) is listed separately in `requirements.txt` as a
comment-only reminder — no `setup.py` or `pyproject.toml` is required for
this single-package library.

## Thread Pool Design
<!-- id: thread-pool-design -->
<!-- require-code-mention: true -->

`ThreadPoolExecutor` was chosen over `asyncio` because:

1. The scheduler is designed for *blocking* callables (DB queries, HTTP
   requests, shell commands). Wrapping these in `asyncio` would require
   `run_in_executor` anyway.
2. `threading.RLock` provides straightforward mutual exclusion for the job
   registry without `asyncio.Lock` ceremony.
3. `max_workers` exposes direct control over concurrency without any event-loop
   integration complexity.

See [[scheduler-engine]] for how the executor is used.

File reference: [[scheduler/scheduler.py#Scheduler]]

## Genesis Resolver Design
<!-- id: genesis-resolver -->
<!-- require-code-mention: true -->

`GenesisResolver` is an optional plugin to the [[scheduler-engine]]:

```
job failure
    │
    ├─ ErrorClassifier.classify(exception) → ErrorCategory
    │      TRANSIENT → RETRY_BACKOFF
    │      CONFIGURATION → ESCALATE
    │      RESOURCE → RETRY_BACKOFF (longer delay)
    │      DEPENDENCY → RETRY_IMMEDIATE
    │      UNKNOWN → falls through to violation check
    │
    └─ ViolationDetector.detect(job, all_jobs) → list[Violation]
           V1 (stale dependency) → SURGICAL_RETRY
           V2 (dependency failed) → ESCALATE
           V3+ → SKIP or ESCALATE
```

`GenesisResolver.resolve()` returns a `ResolutionResult` with a `RecoveryAction`
and optional modified retry delay. [[result-handling]] applies the action.

See [[error-classification]] and [[violation-detection]] for the sub-modules.

File reference: [[scheduler/resolver.py#GenesisResolver]]

## Error Classification
<!-- id: error-classification -->
<!-- require-code-mention: true -->

`ErrorClassifier.classify(exception)` maps exception types to `ErrorCategory`:

| Category | Triggered by |
|----------|-------------|
| `TRANSIENT` | `TimeoutError`, `ConnectionError`, `OSError` subclasses |
| `CONFIGURATION` | `ValueError`, `TypeError`, `AttributeError`, `KeyError` |
| `RESOURCE` | `MemoryError`, `OSError` with errno ENOSPC/ENOMEM |
| `DEPENDENCY` | Custom `DependencyError`, or jobs detected as dependent by [[violation-detection]] |
| `UNKNOWN` | Everything else — defaults to standard retry logic |

Classification is intentionally conservative: when in doubt, `UNKNOWN` is
returned so the scheduler's default behaviour is preserved.

File reference: [[scheduler/resolver.py#ErrorClassifier]]

## Violation Detection
<!-- id: violation-detection -->
<!-- require-code-mention: true -->

`ViolationDetector.detect(job, all_jobs)` inspects the live job graph for
runtime consistency violations. It is **read-only** — it never mutates job
state. Violation types:

| Code | Condition |
|------|-----------|
| V1 | A dependency job is still `PENDING` or `RUNNING` when this job fires |
| V2 | A dependency job is in `FAILED` state |
| V3 | A dependency job is `EXPIRED` (one-time, not completed successfully) |
| V4 | The job has exceeded a configurable retry threshold |
| V5 | The job graph contains an unexpected structural inconsistency |

Results feed into [[genesis-resolver]]'s decision tree.

File reference: [[scheduler/resolver.py#ViolationDetector]]

## Vixie Cron OR Semantics
<!-- id: cron-or-semantics -->
<!-- require-code-mention: true -->

When both the day-of-month and day-of-week fields are restricted (neither is
`*`), `CronExpression._day_matches()` treats them with **OR semantics**: a
candidate datetime matches if *either* the day-of-month **or** the
day-of-week matches. This matches historical Vixie cron behaviour and the
behaviour of most Unix cron implementations.

When only one field is restricted, only that field is checked (standard AND
semantics apply to the remaining fields).

File reference: [[scheduler/cron_parser.py#_day_matches]]
"""

AGENTS_MD = """\
# Agent Instructions

This repository uses a `lat` knowledge graph in `lat.md/`. The graph documents
design decisions, domain concepts, the public API, and test specifications.

## Before You Start

Read the relevant `lat.md/` sections before modifying code. Use:

    python -m lat search <term>      # find relevant sections
    python -m lat section <id>       # display a specific section

For example, before touching retry logic: `python -m lat section job-retry-logic`.

## Before You Finish

Always run:

    python -m lat check

This validates that all `[[wiki links]]` in `lat.md/` resolve, all
`# @lat: [[id]]` source comments point to existing sections, and every
section marked `require-code-mention: true` has at least one source backlink.
Fix any errors reported before committing.

## Annotating Source Changes

When you add or meaningfully modify a function or class that corresponds to a
documented concept, add a `# @lat: [[section-id]]` comment on or just above
the definition. Example:

    class Scheduler:
        # @lat: [[scheduler-engine]]

Then re-run `python -m lat check` to confirm the backlink is valid.

## Adding or Updating Sections

New sections must have a unique `<!-- id: kebab-case-id -->` comment
immediately below the heading. If the concept must have a corresponding code
location, add `<!-- require-code-mention: true -->` on the next line.

To update an existing section, edit the relevant file in `lat.md/` and run
`python -m lat check` afterwards.

## Pre-commit Hook (optional)

To enforce consistency on every commit, add this to `.git/hooks/pre-commit`:

    #!/bin/sh
    python -m lat check
"""
