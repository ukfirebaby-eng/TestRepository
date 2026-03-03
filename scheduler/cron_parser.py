"""
5-field cron expression parser.

Field order: minute hour day month weekday
Supports: *, */n, n, n-m, n,m,n-m combinations, month/weekday name aliases.

Day-of-week/day-of-month OR semantics: if both are restricted (not '*'),
either matching satisfies the constraint (Vixie cron behavior).
"""

from datetime import datetime, timedelta
from typing import Optional


_MONTH_ALIASES = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_WEEKDAY_ALIASES = {
    "sun": 0, "mon": 1, "tue": 2, "wed": 3,
    "thu": 4, "fri": 5, "sat": 6,
}

# (min_val, max_val, aliases)
_FIELD_SPECS = [
    ("minute",  0, 59, {}),
    ("hour",    0, 23, {}),
    ("day",     1, 31, {}),
    ("month",   1, 12, _MONTH_ALIASES),
    ("weekday", 0,  6, _WEEKDAY_ALIASES),
]


class CronParseError(ValueError):
    """Raised when a cron expression cannot be parsed."""


def _parse_field(raw: str, field_name: str, min_val: int, max_val: int,
                 aliases: dict) -> frozenset:
    """Parse a single cron field into a frozenset of matching integers."""
    result = set()
    raw = raw.lower()

    for part in raw.split(","):
        # Replace aliases
        for name, num in aliases.items():
            part = part.replace(name, str(num))

        # Extract step
        if "/" in part:
            range_part, step_str = part.split("/", 1)
            try:
                step = int(step_str)
            except ValueError:
                raise CronParseError(
                    f"Invalid step in field '{field_name}': '{part}'"
                )
            if step < 1:
                raise CronParseError(
                    f"Step must be >= 1 in field '{field_name}': '{part}'"
                )
        else:
            range_part, step = part, 1

        # Extract range or single value
        if range_part == "*":
            lo, hi = min_val, max_val
        elif "-" in range_part:
            parts = range_part.split("-", 1)
            try:
                lo, hi = int(parts[0]), int(parts[1])
            except ValueError:
                raise CronParseError(
                    f"Invalid range in field '{field_name}': '{part}'"
                )
        else:
            try:
                lo = hi = int(range_part)
            except ValueError:
                raise CronParseError(
                    f"Invalid value in field '{field_name}': '{part}'"
                )

        if not (min_val <= lo <= max_val):
            raise CronParseError(
                f"Value {lo} out of range [{min_val},{max_val}] "
                f"in field '{field_name}'"
            )
        if not (min_val <= hi <= max_val):
            raise CronParseError(
                f"Value {hi} out of range [{min_val},{max_val}] "
                f"in field '{field_name}'"
            )
        if lo > hi:
            raise CronParseError(
                f"Range start > end in field '{field_name}': '{part}'"
            )

        result.update(range(lo, hi + 1, step))

    return frozenset(result)


class CronExpression:
    """Parsed 5-field cron expression with next-fire-time computation."""

    def __init__(self, expression: str) -> None:
        self.expression = expression
        fields = expression.strip().split()
        if len(fields) != 5:
            raise CronParseError(
                f"Expected 5 fields, got {len(fields)}: '{expression}'"
            )

        self._minutes  = _parse_field(fields[0], *_FIELD_SPECS[0])
        self._hours    = _parse_field(fields[1], *_FIELD_SPECS[1])
        self._days     = _parse_field(fields[2], *_FIELD_SPECS[2])
        self._months   = _parse_field(fields[3], *_FIELD_SPECS[3])
        self._weekdays = _parse_field(fields[4], *_FIELD_SPECS[4])

        # Track whether day-of-month / day-of-week were restricted
        self._day_restricted     = fields[2] != "*"
        self._weekday_restricted = fields[4] != "*"

    def matches(self, dt: datetime) -> bool:
        """Return True if all fields match the given datetime (ignores seconds)."""
        if dt.minute not in self._minutes:
            return False
        if dt.hour not in self._hours:
            return False
        if dt.month not in self._months:
            return False
        return self._day_matches(dt)

    def _day_matches(self, dt: datetime) -> bool:
        """Evaluate day-of-month / day-of-week with OR semantics."""
        dom_match = dt.day in self._days
        # Convert Python weekday (Mon=0..Sun=6) to cron weekday (Sun=0..Sat=6)
        cron_dow = (dt.weekday() + 1) % 7
        dow_match = cron_dow in self._weekdays

        if self._day_restricted and self._weekday_restricted:
            # OR semantics: either constraint satisfied is enough
            return dom_match or dow_match
        elif self._day_restricted:
            return dom_match
        elif self._weekday_restricted:
            return dow_match
        return True  # both are '*'

    def next_after(self, after: datetime) -> datetime:
        """
        Return the smallest datetime strictly after `after` where all fields match.

        Uses a field-carry forward search: start 1 minute after `after`,
        then advance coarsely (by month, day, hour) when a field doesn't match.
        Caps search at 4 years to guard against impossible expressions.
        """
        # Start at the next minute, zeroing sub-minute precision
        candidate = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
        deadline = after.replace(year=after.year + 4)

        while candidate <= deadline:
            # ---- month ----
            if candidate.month not in self._months:
                # Advance to the first day of the next matching month
                candidate = self._next_matching_month(candidate)
                continue

            # ---- day (with weekday OR semantics) ----
            if not self._day_matches(candidate):
                candidate = candidate.replace(hour=0, minute=0) + timedelta(days=1)
                continue

            # ---- hour ----
            if candidate.hour not in self._hours:
                candidate = self._next_matching_hour(candidate)
                continue

            # ---- minute ----
            if candidate.minute not in self._minutes:
                candidate = self._next_matching_minute(candidate)
                continue

            # All fields match
            return candidate

        raise CronParseError(
            f"No valid fire time found within 4 years for expression: "
            f"'{self.expression}'"
        )

    # ------------------------------------------------------------------
    # Internal helpers for coarse advancement
    # ------------------------------------------------------------------

    def _next_matching_month(self, dt: datetime) -> datetime:
        """Advance dt to the 1st of the next month in _months, reset day/hr/min."""
        month = dt.month + 1
        year = dt.year
        while True:
            if month > 12:
                month = 1
                year += 1
            if month in self._months:
                return datetime(year, month, 1, 0, 0)
            month += 1

    def _next_matching_hour(self, dt: datetime) -> datetime:
        """Advance dt to the next hour in _hours, reset minute."""
        hour = dt.hour + 1
        day = dt.day
        month = dt.month
        year = dt.year
        if hour > 23:
            # Roll over to next day
            return dt.replace(hour=0, minute=0) + timedelta(days=1)
        while hour <= 23:
            if hour in self._hours:
                return dt.replace(hour=hour, minute=0)
            hour += 1
        return dt.replace(hour=0, minute=0) + timedelta(days=1)

    def _next_matching_minute(self, dt: datetime) -> datetime:
        """Advance dt to the next minute in _minutes."""
        minute = dt.minute + 1
        if minute > 59:
            return dt.replace(minute=0) + timedelta(hours=1)
        while minute <= 59:
            if minute in self._minutes:
                return dt.replace(minute=minute)
            minute += 1
        return dt.replace(minute=0) + timedelta(hours=1)
