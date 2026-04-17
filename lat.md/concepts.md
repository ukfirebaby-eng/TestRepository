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
