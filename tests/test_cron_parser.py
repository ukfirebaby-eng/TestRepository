"""Tests for the cron expression parser."""

import unittest
from datetime import datetime

from scheduler.cron_parser import CronExpression, CronParseError, _parse_field


class TestParseField(unittest.TestCase):

    def _parse(self, raw, min_val=0, max_val=59, aliases=None):
        return _parse_field(raw, "test", min_val, max_val, aliases or {})

    def test_wildcard(self):
        result = self._parse("*", 0, 5)
        self.assertEqual(result, frozenset({0, 1, 2, 3, 4, 5}))

    def test_single_value(self):
        result = self._parse("5")
        self.assertIn(5, result)
        self.assertEqual(len(result), 1)

    def test_range(self):
        result = self._parse("1-5", 0, 59)
        self.assertEqual(result, frozenset({1, 2, 3, 4, 5}))

    def test_step_from_wildcard(self):
        result = self._parse("*/15", 0, 59)
        self.assertEqual(result, frozenset({0, 15, 30, 45}))

    def test_step_from_range(self):
        result = self._parse("0-30/10", 0, 59)
        self.assertEqual(result, frozenset({0, 10, 20, 30}))

    def test_comma_list(self):
        result = self._parse("1,3,5", 0, 59)
        self.assertEqual(result, frozenset({1, 3, 5}))

    def test_comma_with_ranges(self):
        result = self._parse("1-3,7,10-12", 0, 59)
        self.assertEqual(result, frozenset({1, 2, 3, 7, 10, 11, 12}))

    def test_month_aliases(self):
        from scheduler.cron_parser import _MONTH_ALIASES
        result = _parse_field("jan-mar", "month", 1, 12, _MONTH_ALIASES)
        self.assertEqual(result, frozenset({1, 2, 3}))

    def test_weekday_aliases(self):
        from scheduler.cron_parser import _WEEKDAY_ALIASES
        result = _parse_field("mon,wed,fri", "weekday", 0, 6, _WEEKDAY_ALIASES)
        self.assertEqual(result, frozenset({1, 3, 5}))

    def test_out_of_range_raises(self):
        with self.assertRaises(CronParseError):
            self._parse("60", 0, 59)  # minute 60 invalid

    def test_negative_step_raises(self):
        with self.assertRaises(CronParseError):
            self._parse("*/-1", 0, 59)

    def test_zero_step_raises(self):
        with self.assertRaises(CronParseError):
            self._parse("*/0", 0, 59)

    def test_invalid_range_order_raises(self):
        with self.assertRaises(CronParseError):
            self._parse("5-3", 0, 59)


class TestCronExpression(unittest.TestCase):

    def test_wrong_field_count_raises(self):
        with self.assertRaises(CronParseError):
            CronExpression("* * * *")  # 4 fields

    def test_wrong_field_count_too_many(self):
        with self.assertRaises(CronParseError):
            CronExpression("* * * * * *")  # 6 fields

    def test_matches_every_minute(self):
        expr = CronExpression("* * * * *")
        dt = datetime(2024, 6, 15, 10, 30)
        self.assertTrue(expr.matches(dt))

    def test_specific_match(self):
        expr = CronExpression("30 14 * * *")
        self.assertTrue(expr.matches(datetime(2024, 1, 1, 14, 30)))
        self.assertFalse(expr.matches(datetime(2024, 1, 1, 14, 31)))
        self.assertFalse(expr.matches(datetime(2024, 1, 1, 15, 30)))

    def test_next_after_every_minute(self):
        expr = CronExpression("* * * * *")
        after = datetime(2024, 6, 15, 10, 30, 45)
        nxt = expr.next_after(after)
        self.assertEqual(nxt, datetime(2024, 6, 15, 10, 31))

    def test_next_after_specific_time_today(self):
        expr = CronExpression("30 14 * * *")
        after = datetime(2024, 6, 15, 13, 0)
        nxt = expr.next_after(after)
        self.assertEqual(nxt, datetime(2024, 6, 15, 14, 30))

    def test_next_after_specific_time_tomorrow(self):
        expr = CronExpression("30 14 * * *")
        after = datetime(2024, 6, 15, 15, 0)
        nxt = expr.next_after(after)
        self.assertEqual(nxt, datetime(2024, 6, 16, 14, 30))

    def test_next_after_month_rollover(self):
        expr = CronExpression("0 0 1 3 *")  # 1st March midnight
        after = datetime(2024, 4, 1, 0, 0)   # April - past March
        nxt = expr.next_after(after)
        self.assertEqual(nxt, datetime(2025, 3, 1, 0, 0))

    def test_next_after_weekday_monday(self):
        # "0 9 * * 1" = 9am every Monday
        # datetime.weekday(): Mon=0, but cron: Mon=1
        expr = CronExpression("0 9 * * 1")
        # Start on a Wednesday 2024-06-12
        after = datetime(2024, 6, 12, 9, 0)  # Wednesday
        nxt = expr.next_after(after)
        # Next Monday is 2024-06-17
        self.assertEqual(nxt.strftime("%A"), "Monday")
        self.assertEqual(nxt.hour, 9)
        self.assertEqual(nxt.minute, 0)

    def test_next_after_step_expression(self):
        expr = CronExpression("*/15 * * * *")  # every 15 minutes
        after = datetime(2024, 6, 15, 10, 10)
        nxt = expr.next_after(after)
        self.assertEqual(nxt, datetime(2024, 6, 15, 10, 15))

    def test_next_after_advances_past_after(self):
        """next_after must be strictly AFTER `after`."""
        expr = CronExpression("30 14 * * *")
        # Exactly at 14:30 - next should be tomorrow
        after = datetime(2024, 6, 15, 14, 30, 0)
        nxt = expr.next_after(after)
        self.assertGreater(nxt, after)

    def test_leap_year_feb29(self):
        expr = CronExpression("0 0 29 2 *")  # Feb 29 midnight
        after = datetime(2024, 2, 28, 0, 0)  # 2024 is a leap year
        nxt = expr.next_after(after)
        self.assertEqual(nxt, datetime(2024, 2, 29, 0, 0))

    def test_day_and_weekday_or_semantics(self):
        """When both day-of-month and weekday are restricted, OR applies."""
        # day=15 OR weekday=Monday(1)
        expr = CronExpression("0 0 15 * 1")
        # On the 15th (even if not Monday) should match
        dt = datetime(2024, 6, 15, 0, 0)  # 15th June 2024 (Saturday)
        self.assertTrue(expr.matches(dt))


class TestCronExpressionNextAfterVariants(unittest.TestCase):
    """Additional edge cases for next_after."""

    def test_hourly(self):
        expr = CronExpression("0 * * * *")
        after = datetime(2024, 1, 1, 10, 30)
        nxt = expr.next_after(after)
        self.assertEqual(nxt, datetime(2024, 1, 1, 11, 0))

    def test_daily_midnight(self):
        expr = CronExpression("0 0 * * *")
        after = datetime(2024, 1, 1, 10, 30)
        nxt = expr.next_after(after)
        self.assertEqual(nxt, datetime(2024, 1, 2, 0, 0))

    def test_year_boundary(self):
        expr = CronExpression("0 0 1 1 *")  # Jan 1 midnight
        after = datetime(2024, 6, 1, 0, 0)
        nxt = expr.next_after(after)
        self.assertEqual(nxt, datetime(2025, 1, 1, 0, 0))


if __name__ == "__main__":
    unittest.main()
