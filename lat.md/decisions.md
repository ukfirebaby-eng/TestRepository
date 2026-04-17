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
