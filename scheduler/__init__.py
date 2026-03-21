"""
Simple Job Scheduler
====================

Public API::

    from scheduler import Scheduler, Job, JobStatus
    from scheduler import IntervalSchedule, CronSchedule, OneTimeSchedule

Quick start::

    from scheduler import Scheduler, Job, IntervalSchedule

    def my_task():
        print("Running!")

    s = Scheduler()
    s.add_job(Job("my_task", my_task, IntervalSchedule(seconds=30)))
    s.start()
"""

from .cron_parser import CronExpression, CronParseError
from .job import Job, JobResult, JobStatus
from .resolver import (
    ErrorCategory,
    ErrorClassifier,
    GenesisResolver,
    RecoveryAction,
    ResolutionResult,
    Violation,
    ViolationDetector,
    ViolationType,
)
from .schedules import CronSchedule, IntervalSchedule, OneTimeSchedule, Schedule
from .scheduler import (
    CircularDependencyError,
    DuplicateJobError,
    JobNotFoundError,
    Scheduler,
)

__all__ = [
    # Core
    "Scheduler",
    "Job",
    "JobStatus",
    "JobResult",
    # Schedules
    "Schedule",
    "IntervalSchedule",
    "CronSchedule",
    "OneTimeSchedule",
    # Errors
    "CircularDependencyError",
    "CronParseError",
    "DuplicateJobError",
    "JobNotFoundError",
    # Low-level cron
    "CronExpression",
    # Genesis Resolver
    "GenesisResolver",
    "ErrorClassifier",
    "ErrorCategory",
    "ViolationDetector",
    "ViolationType",
    "Violation",
    "RecoveryAction",
    "ResolutionResult",
]
