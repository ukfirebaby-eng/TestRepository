"""
Main Scheduler engine.

Manages the job registry, dependency graph validation, scheduling loop,
and concurrent job execution via a ThreadPoolExecutor.
"""

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Set

from .job import Job, JobStatus
from .resolver import GenesisResolver, RecoveryAction
from .schedules import Schedule

logger = logging.getLogger(__name__)


class CircularDependencyError(ValueError):
    """Raised when adding a job would create a circular dependency."""

    def __init__(self, cycle: List[str]) -> None:
        self.cycle = cycle
        super().__init__(f"Circular dependency detected: {' -> '.join(cycle)}")


class DuplicateJobError(ValueError):
    """Raised when a job with the same name already exists."""


class JobNotFoundError(KeyError):
    """Raised when referencing a job name that does not exist."""


class Scheduler:  # @lat: [[scheduler-engine]]
    """
    Central scheduler engine.

    Usage::

        scheduler = Scheduler()
        scheduler.add_job(Job("my_job", func, IntervalSchedule(seconds=30)))
        scheduler.start()
        # ... later ...
        scheduler.stop()
    """

    def __init__(
        self,
        max_workers: int = 4,
        tick_interval: float = 1.0,
        clock: Optional[Callable[[], datetime]] = None,
        resolver: Optional[GenesisResolver] = None,
    ) -> None:
        """
        Args:
            max_workers:    Thread pool size for concurrent job execution.
            tick_interval:  Seconds between scheduling loop iterations.
            clock:          Injectable clock function (defaults to datetime.now).
                            Useful for deterministic testing.
            resolver:       Optional :class:`~scheduler.resolver.GenesisResolver`
                            for intelligent failure recovery.  When provided,
                            the resolver's verdict overrides the default
                            retry/fail logic in :meth:`_handle_result`.
        """
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.RLock()
        self._futures: Dict[str, Future] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers)  # @lat: [[thread-pool-design]]
        self._stop_event = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None
        self._tick_interval = tick_interval
        self._clock = clock or datetime.now  # @lat: [[injectable-clock]]
        self._resolver = resolver

    # ------------------------------------------------------------------
    # Job registration
    # ------------------------------------------------------------------

    def add_job(self, job: Job) -> Job:
        """
        Register a job with the scheduler.

        Validates:
          - No duplicate job name.
          - All dependency names refer to existing jobs.
          - Adding this job does not create a circular dependency.

        Computes the initial next_run time and returns the job.
        """
        with self._lock:
            if job.name in self._jobs:
                raise DuplicateJobError(
                    f"A job named {job.name!r} already exists"
                )
            for dep in job.dependencies:
                if dep not in self._jobs:
                    raise JobNotFoundError(
                        f"Dependency {dep!r} not found for job {job.name!r}"
                    )

            # Temporarily add to check for cycles
            self._jobs[job.name] = job
            try:
                self._check_for_cycle(job.name)
            except CircularDependencyError:
                del self._jobs[job.name]
                raise

            job.initialize_next_run(self._clock())
            logger.info("Registered job %r (%s)", job.name, job.schedule.description())
            return job

    def remove_job(self, name: str) -> None:
        """
        Remove a job from the scheduler.

        Raises JobNotFoundError if the name does not exist.
        Raises ValueError if another job depends on this job.
        """
        with self._lock:
            if name not in self._jobs:
                raise JobNotFoundError(f"Job {name!r} not found")
            dependents = [
                j.name for j in self._jobs.values()
                if name in j.dependencies and j.name != name
            ]
            if dependents:
                raise ValueError(
                    f"Cannot remove job {name!r}: jobs {dependents} depend on it"
                )
            del self._jobs[name]
            logger.info("Removed job %r", name)

    def get_job(self, name: str) -> Job:
        """Return the Job with the given name, or raise JobNotFoundError."""
        with self._lock:
            if name not in self._jobs:
                raise JobNotFoundError(f"Job {name!r} not found")
            return self._jobs[name]

    def list_jobs(self) -> List[Job]:
        """Return a snapshot list of all registered jobs."""
        with self._lock:
            return list(self._jobs.values())

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background scheduling loop thread. Idempotent."""
        if self._loop_thread is not None and self._loop_thread.is_alive():
            return
        self._stop_event.clear()
        self._loop_thread = threading.Thread(
            target=self._scheduling_loop,
            name="scheduler-loop",
            daemon=True,
        )
        self._loop_thread.start()
        logger.info("Scheduler started")

    def stop(self, wait: bool = True) -> None:
        """
        Signal the scheduling loop to stop.

        Args:
            wait: If True (default), block until the loop thread exits.
        """
        self._stop_event.set()
        if wait and self._loop_thread is not None:
            self._loop_thread.join()
        logger.info("Scheduler stopped")

    def run_blocking(self) -> None:
        """Run the scheduling loop in the calling thread (blocks until stop())."""
        self._stop_event.clear()
        logger.info("Scheduler running (blocking)")
        self._scheduling_loop()

    # ------------------------------------------------------------------
    # Internal scheduling loop
    # ------------------------------------------------------------------

    def _scheduling_loop(self) -> None:  # @lat: [[scheduler-loop]]
        while not self._stop_event.is_set():
            tick_start = self._clock()

            with self._lock:
                completed = self._completed_job_names()

                # Process futures that have finished
                for name, future in list(self._futures.items()):
                    if future.done():
                        del self._futures[name]
                        job = self._jobs.get(name)
                        if job is not None:
                            # JobResult is stored in history by job.run()
                            result = job.history[-1] if job.history else None
                            if result is not None:
                                self._handle_result(job, result)

                # Submit newly ready jobs
                for job in self._jobs.values():
                    if job.name not in self._futures and job.is_ready(tick_start, completed):
                        future = self._executor.submit(self._run_job, job)
                        self._futures[job.name] = future
                        logger.debug("Submitted job %r", job.name)

            # Sleep for remainder of tick interval, waking early if stopped
            elapsed = (datetime.now() - tick_start).total_seconds()
            sleep_time = max(0.0, self._tick_interval - elapsed)
            self._stop_event.wait(timeout=sleep_time)

    def _run_job(self, job: Job) -> None:
        """Execute the job and capture the result (runs in thread pool)."""
        logger.info("Running job %r", job.name)
        result = job.run()
        if result.success:
            logger.info("Job %r completed successfully", job.name)
        else:
            logger.warning(
                "Job %r failed: %s", job.name, result.exception
            )

    def _handle_result(self, job: Job, result) -> None:  # @lat: [[result-handling]]
        """
        Process the outcome of a completed job execution.

        Called while holding self._lock.
        Decides whether to mark completed, retry, or reschedule.

        When a :class:`~scheduler.resolver.GenesisResolver` is configured,
        its verdict takes precedence over the default retry/fail logic:

        * ``RETRY_IMMEDIATE`` / ``RETRY_BACKOFF`` / ``SURGICAL_RETRY`` —
          schedules a retry at the resolver-specified delay.
        * ``SKIP`` / ``ESCALATE`` — marks the job FAILED and reschedules
          for its next natural fire time (if any).
        """
        if result.success:
            job.mark_completed()
            nxt = job.compute_next_run(result.finished_at)
            if nxt is None:
                logger.info("Job %r expired (one-time schedule)", job.name)
            else:
                logger.debug("Job %r rescheduled for %s", job.name, nxt)
            return

        # --- failure path ---------------------------------------------------
        if self._resolver is not None:
            resolution = self._resolver.resolve(job, self._jobs)
            action = resolution.action
            delay = (
                resolution.modified_retry_delay
                if resolution.modified_retry_delay is not None
                else job.retry_delay_seconds
            )

            if action in (
                RecoveryAction.RETRY_IMMEDIATE,
                RecoveryAction.RETRY_BACKOFF,
                RecoveryAction.SURGICAL_RETRY,
            ):
                retry_at = result.finished_at + timedelta(seconds=delay)
                job.schedule_retry(retry_at)
                logger.info(
                    "Job %r — resolver action=%s, retry at %s",
                    job.name, action.value, retry_at,
                )
            else:
                # SKIP or ESCALATE: mark failed, still allow future schedule ticks
                job.mark_failed()
                if action == RecoveryAction.ESCALATE:
                    logger.error(
                        "Job %r escalated after %d attempt(s): %s",
                        job.name, len(job.history), resolution.details,
                    )
                nxt = job.compute_next_run(result.finished_at)
                if nxt is not None:
                    job.status = JobStatus.PENDING
                    logger.warning(
                        "Job %r failed (%s), rescheduled for %s",
                        job.name, action.value, nxt,
                    )
                elif job.status == JobStatus.EXPIRED:
                    # compute_next_run set EXPIRED on a failed one-time job;
                    # revert so dependent jobs don't treat this as a success.
                    job.status = JobStatus.FAILED
        else:
            # Default behaviour (no resolver configured)
            if job.retry_count < job.max_retries:
                retry_at = result.finished_at + timedelta(
                    seconds=job.retry_delay_seconds
                )
                job.schedule_retry(retry_at)
                logger.warning(
                    "Job %r failed, retry %d/%d at %s",
                    job.name, job.retry_count, job.max_retries, retry_at,
                )
            else:
                job.mark_failed()
                # Still reschedule per schedule so future runs can happen
                nxt = job.compute_next_run(result.finished_at)
                if nxt is not None:
                    job.status = JobStatus.PENDING
                    logger.warning(
                        "Job %r failed (retries exhausted), rescheduled for %s",
                        job.name, nxt,
                    )
                elif job.status == JobStatus.EXPIRED:
                    # compute_next_run set EXPIRED on a failed one-time job;
                    # revert so dependent jobs don't treat this as a success.
                    job.status = JobStatus.FAILED

    # ------------------------------------------------------------------
    # Dependency graph helpers
    # ------------------------------------------------------------------

    def _completed_job_names(self) -> Set[str]:
        """Return names of jobs that have completed successfully (COMPLETED or EXPIRED)."""
        return {
            name for name, job in self._jobs.items()
            if job.status in (JobStatus.COMPLETED, JobStatus.EXPIRED)
        }

    def _check_for_cycle(self, start: str) -> None:  # @lat: [[dependency-graph]]
        """
        DFS cycle detection starting from `start`.

        Raises CircularDependencyError if a cycle is found.
        Must be called while holding self._lock.
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {name: WHITE for name in self._jobs}
        path: List[str] = []

        def dfs(node: str) -> None:
            color[node] = GRAY
            path.append(node)
            for dep in self._jobs[node].dependencies:
                if color.get(dep, WHITE) == GRAY:
                    cycle_start = path.index(dep)
                    raise CircularDependencyError(path[cycle_start:] + [dep])
                if color.get(dep, WHITE) == WHITE:
                    dfs(dep)
            path.pop()
            color[node] = BLACK

        dfs(start)
