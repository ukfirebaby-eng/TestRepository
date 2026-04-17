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
