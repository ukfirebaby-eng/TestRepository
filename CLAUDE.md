# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
python -m pytest tests/

# Run a single test file
python -m pytest tests/test_scheduler.py -v

# Run a single test by name
python -m pytest tests/test_scheduler.py::TestScheduler::test_add_job -v

# Validate the knowledge graph (run before finishing any task)
python -m lat check
```

No build step — pure Python 3.11+ stdlib. No linter is configured.

## Architecture

The library is a single `scheduler/` package. `Scheduler` is the central engine: it owns a `dict[str, Job]` registry protected by an `RLock`, a `ThreadPoolExecutor` for concurrent job execution, and a background thread running `_scheduling_loop()`. The loop ticks at `tick_interval` seconds, drains completed futures, then submits any `Job` where `is_ready()` returns `True`.

**Execution flow:** `_scheduling_loop` → `_run_job` (in thread pool) → `job.run()` captures result → `_handle_result` decides retry/complete/fail. When a `GenesisResolver` is configured it overrides the default retry logic; otherwise `retry_count < max_retries` drives retries.

**Job readiness** has three gates: `status == PENDING`, `next_run <= now`, and all dependency names in the completed-job set. Dependencies form a DAG validated by DFS cycle detection on every `add_job` call.

**Schedule types** (`schedules.py`) delegate to `CronExpression` (`cron_parser.py`) for cron scheduling. `CronExpression._day_matches` uses Vixie cron OR semantics: when both day-of-month and day-of-week are restricted, either match is sufficient.

**GenesisResolver** (`resolver.py`) is an optional failure-recovery plugin composed of two read-only sub-modules: `ErrorClassifier` maps exceptions to `ErrorCategory` values, and `ViolationDetector` inspects the live job graph for V1–V5 violations. The resolver's `RecoveryAction` verdict is applied by `_handle_result`.

**Injectable clock:** `Scheduler(clock=...)` replaces `datetime.now` throughout. Tests use this to control time without sleeping.

## Knowledge Graph

This repo uses `lat.md/` — a set of interconnected markdown files documenting design decisions, domain concepts, and API contracts. Before touching unfamiliar code, orient yourself with:

```bash
python -m lat search <term>   # find relevant sections
python -m lat section <id>    # read a specific section
```

Key section ids: `scheduler-engine`, `scheduler-loop`, `result-handling`, `dependency-graph`, `job-model`, `job-status`, `job-readiness`, `job-retry-logic`, `schedule-types`, `cron-expression`, `genesis-resolver`, `error-classification`, `violation-detection`.

When you modify or add a class/function that maps to a documented concept, add `# @lat: [[section-id]]` on or just above the definition. Run `python -m lat check` before finishing — it exits 1 if any cross-references are broken. Use `/lat` to run the full post-task sync workflow.
