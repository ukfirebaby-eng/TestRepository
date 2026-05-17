# TestRepository — Job Scheduler

Python 3.11+ cron-based job scheduler using stdlib only (no external runtime deps).

## Project layout

```
scheduler/        core library
  scheduler.py    Scheduler engine (ThreadPoolExecutor, dependency graph)
  job.py          Job / JobStatus dataclasses
  schedules.py    Schedule types (cron, interval, one-shot)
  cron_parser.py  Cron expression parser
  resolver.py     GenesisResolver — startup/recovery logic
tests/            pytest suite mirroring scheduler/ modules
examples/         example_usage.py — runnable demo
requirements.txt  stdlib only; dev: pip install pytest
```

## Commands

```bash
pytest                   # run all tests
pytest tests/test_X.py   # single module
python examples/example_usage.py
```

## Key invariants

- `Scheduler` manages a DAG of `Job` objects; adding a cycle raises `CircularDependencyError`.
- `Job.status` transitions: PENDING → RUNNING → COMPLETED | FAILED | EXPIRED.
- All public surface is in `scheduler/__init__.py`.
