"""
Job class and related types.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, List, Optional

from .schedules import Schedule


class JobStatus(Enum):
    PENDING   = "pending"    # Waiting for next scheduled time or dependencies
    RUNNING   = "running"    # Currently executing
    COMPLETED = "completed"  # Last execution succeeded
    FAILED    = "failed"     # Last execution raised an exception
    EXPIRED   = "expired"    # One-time job that has already fired


@dataclass
class JobResult:
    """Immutable record of a single execution attempt."""
    job_name: str
    started_at: datetime
    finished_at: datetime
    success: bool
    return_value: Any = None
    exception: Optional[Exception] = None


class Job:
    """
    A schedulable unit of work.

    Thread-safe: mutable state is guarded by an internal RLock.
    """

    def __init__(
        self,
        name: str,
        func: Callable[..., Any],
        schedule: Schedule,
        *,
        args: tuple = (),
        kwargs: Optional[dict] = None,
        dependencies: Optional[List[str]] = None,
        max_retries: int = 0,
        retry_delay_seconds: float = 5.0,
    ) -> None:
        self.name = name
        self.func = func
        self.schedule = schedule
        self.args = args
        self.kwargs = kwargs if kwargs is not None else {}
        self.dependencies: List[str] = dependencies if dependencies is not None else []
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

        # Runtime state
        self.status: JobStatus = JobStatus.PENDING
        self.next_run: Optional[datetime] = None
        self.last_run: Optional[datetime] = None
        self.retry_count: int = 0
        self.history: List[JobResult] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # State queries (thread-safe)
    # ------------------------------------------------------------------

    def is_ready(self, now: datetime, completed_names: set) -> bool:
        """
        Return True if this job is eligible to run right now.

        Conditions:
          - status is PENDING
          - next_run is set and <= now
          - all dependencies are in completed_names
        """
        with self._lock:
            if self.status != JobStatus.PENDING:
                return False
            if self.next_run is None or self.next_run > now:
                return False
            return all(dep in completed_names for dep in self.dependencies)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self) -> JobResult:
        """
        Execute the job's callable.

        Sets status to RUNNING before calling, then updates to COMPLETED
        or FAILED after. Never raises; exceptions are captured in the result.
        """
        started_at = datetime.now()
        with self._lock:
            self.status = JobStatus.RUNNING
            self.last_run = started_at

        return_value = None
        exception = None
        success = False

        try:
            return_value = self.func(*self.args, **self.kwargs)
            success = True
        except Exception as exc:
            exception = exc

        finished_at = datetime.now()
        result = JobResult(
            job_name=self.name,
            started_at=started_at,
            finished_at=finished_at,
            success=success,
            return_value=return_value,
            exception=exception,
        )

        with self._lock:
            self.history.append(result)

        return result

    # ------------------------------------------------------------------
    # Next-run scheduling
    # ------------------------------------------------------------------

    def compute_next_run(self, after: datetime) -> Optional[datetime]:
        """
        Ask the schedule for the next fire time after `after`.

        For OneTimeSchedule, marks the schedule triggered and returns None
        if the schedule is exhausted.  Updates self.next_run.
        """
        from .schedules import OneTimeSchedule

        with self._lock:
            if isinstance(self.schedule, OneTimeSchedule):
                self.schedule.mark_triggered()

            nxt = self.schedule.next_run(after)
            self.next_run = nxt
            if nxt is None:
                self.status = JobStatus.EXPIRED
            return nxt

    def initialize_next_run(self, now: datetime) -> None:
        """Set the initial next_run when the job is first registered."""
        from .schedules import OneTimeSchedule

        with self._lock:
            if isinstance(self.schedule, OneTimeSchedule):
                # For one-time jobs, next_run is the run_at time
                nxt = self.schedule.next_run(now - __import__("datetime").timedelta(seconds=1))
            else:
                nxt = self.schedule.next_run(now)
            self.next_run = nxt

    # ------------------------------------------------------------------
    # Status updates (called by the scheduler)
    # ------------------------------------------------------------------

    def mark_completed(self) -> None:
        with self._lock:
            self.status = JobStatus.COMPLETED
            self.retry_count = 0

    def mark_failed(self) -> None:
        with self._lock:
            self.status = JobStatus.FAILED

    def schedule_retry(self, retry_at: datetime) -> None:
        """Put the job back into PENDING for a retry at the given time."""
        with self._lock:
            self.retry_count += 1
            self.next_run = retry_at
            self.status = JobStatus.PENDING

    def __repr__(self) -> str:
        return (
            f"Job(name={self.name!r}, status={self.status.value}, "
            f"next_run={self.next_run}, schedule={self.schedule.description()})"
        )
