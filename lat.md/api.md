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
