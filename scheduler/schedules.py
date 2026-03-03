"""
Schedule types for the job scheduler.

Three concrete schedule types:
  - IntervalSchedule: run repeatedly at a fixed time delta
  - CronSchedule:     run according to a 5-field cron expression
  - OneTimeSchedule:  run exactly once at a specific datetime
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from math import ceil
from typing import Optional

from .cron_parser import CronExpression, CronParseError  # noqa: F401 – re-export


class Schedule(ABC):
    """Abstract base for all schedule types."""

    @abstractmethod
    def next_run(self, after: datetime) -> Optional[datetime]:
        """
        Return the next datetime this schedule should fire after `after`.

        Returns None if the schedule will never fire again.
        """

    @abstractmethod
    def description(self) -> str:
        """Human-readable description of the schedule."""


class IntervalSchedule(Schedule):
    """Run repeatedly at a fixed interval."""

    def __init__(self, seconds: int = 0, minutes: int = 0,
                 hours: int = 0, days: int = 0) -> None:
        self._interval = timedelta(
            days=days, hours=hours, minutes=minutes, seconds=seconds
        )
        if self._interval.total_seconds() <= 0:
            raise ValueError("IntervalSchedule interval must be positive")

    @property
    def interval(self) -> timedelta:
        return self._interval

    def next_run(self, after: datetime) -> datetime:
        """
        Return the next fire time anchored to `after + interval`.

        This does not drift: each call is O(1) and anchored to `after`
        rather than accumulating from a start time.
        """
        return after + self._interval

    def description(self) -> str:
        total = int(self._interval.total_seconds())
        parts = []
        if total >= 86400:
            parts.append(f"{total // 86400}d")
            total %= 86400
        if total >= 3600:
            parts.append(f"{total // 3600}h")
            total %= 3600
        if total >= 60:
            parts.append(f"{total // 60}m")
            total %= 60
        if total:
            parts.append(f"{total}s")
        return f"every {' '.join(parts)}"


class CronSchedule(Schedule):
    """Run according to a 5-field cron expression."""

    def __init__(self, expression: str) -> None:
        self._expr = CronExpression(expression)  # raises CronParseError if invalid

    @property
    def expression(self) -> str:
        return self._expr.expression

    def next_run(self, after: datetime) -> datetime:
        return self._expr.next_after(after)

    def description(self) -> str:
        return f"cron '{self.expression}'"


class OneTimeSchedule(Schedule):
    """Run exactly once at a specific datetime."""

    def __init__(self, run_at: datetime) -> None:
        self._run_at = run_at
        self._triggered = False

    @property
    def run_at(self) -> datetime:
        return self._run_at

    @property
    def triggered(self) -> bool:
        return self._triggered

    def mark_triggered(self) -> None:
        """Called by the scheduler after the job fires."""
        self._triggered = True

    def next_run(self, after: datetime) -> Optional[datetime]:
        if self._triggered or self._run_at <= after:
            return None
        return self._run_at

    def description(self) -> str:
        return f"once at {self._run_at.isoformat()}"
