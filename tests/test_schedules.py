"""Tests for schedule types."""

import unittest
from datetime import datetime, timedelta

from scheduler.schedules import CronSchedule, IntervalSchedule, OneTimeSchedule
from scheduler.cron_parser import CronParseError


class TestIntervalSchedule(unittest.TestCase):

    def test_next_run_adds_interval(self):
        sched = IntervalSchedule(seconds=30)
        after = datetime(2024, 1, 1, 10, 0, 0)
        nxt = sched.next_run(after)
        self.assertEqual(nxt, datetime(2024, 1, 1, 10, 0, 30))

    def test_interval_minutes(self):
        sched = IntervalSchedule(minutes=5)
        after = datetime(2024, 1, 1, 10, 0, 0)
        nxt = sched.next_run(after)
        self.assertEqual(nxt, datetime(2024, 1, 1, 10, 5, 0))

    def test_interval_hours(self):
        sched = IntervalSchedule(hours=2)
        after = datetime(2024, 1, 1, 10, 0, 0)
        nxt = sched.next_run(after)
        self.assertEqual(nxt, datetime(2024, 1, 1, 12, 0, 0))

    def test_interval_combined(self):
        sched = IntervalSchedule(hours=1, minutes=30, seconds=15)
        after = datetime(2024, 1, 1, 10, 0, 0)
        nxt = sched.next_run(after)
        self.assertEqual(nxt, datetime(2024, 1, 1, 11, 30, 15))

    def test_zero_interval_raises(self):
        with self.assertRaises(ValueError):
            IntervalSchedule()  # all zeros

    def test_interval_property(self):
        sched = IntervalSchedule(minutes=10)
        self.assertEqual(sched.interval, timedelta(minutes=10))

    def test_never_returns_none(self):
        sched = IntervalSchedule(seconds=1)
        result = sched.next_run(datetime.now())
        self.assertIsNotNone(result)

    def test_description(self):
        sched = IntervalSchedule(hours=1, minutes=30)
        desc = sched.description()
        self.assertIn("1h", desc)
        self.assertIn("30m", desc)


class TestCronSchedule(unittest.TestCase):

    def test_invalid_expression_raises(self):
        with self.assertRaises(CronParseError):
            CronSchedule("not a cron expression")

    def test_never_returns_none(self):
        sched = CronSchedule("* * * * *")
        result = sched.next_run(datetime.now())
        self.assertIsNotNone(result)

    def test_expression_property(self):
        sched = CronSchedule("*/5 * * * *")
        self.assertEqual(sched.expression, "*/5 * * * *")

    def test_next_run_is_after_input(self):
        sched = CronSchedule("* * * * *")
        after = datetime(2024, 6, 15, 10, 30, 45)
        nxt = sched.next_run(after)
        self.assertGreater(nxt, after)

    def test_description(self):
        sched = CronSchedule("0 9 * * 1")
        self.assertIn("0 9 * * 1", sched.description())


class TestOneTimeSchedule(unittest.TestCase):

    def test_returns_run_at_before_triggered(self):
        run_at = datetime(2024, 12, 25, 9, 0)
        sched = OneTimeSchedule(run_at)
        after = datetime(2024, 12, 24, 0, 0)
        nxt = sched.next_run(after)
        self.assertEqual(nxt, run_at)

    def test_returns_none_after_triggered(self):
        run_at = datetime(2024, 12, 25, 9, 0)
        sched = OneTimeSchedule(run_at)
        sched.mark_triggered()
        after = datetime(2024, 12, 24, 0, 0)
        nxt = sched.next_run(after)
        self.assertIsNone(nxt)

    def test_returns_none_if_run_at_in_past(self):
        run_at = datetime(2024, 1, 1, 0, 0)
        sched = OneTimeSchedule(run_at)
        after = datetime(2024, 6, 1, 0, 0)  # after the run_at
        nxt = sched.next_run(after)
        self.assertIsNone(nxt)

    def test_triggered_property(self):
        sched = OneTimeSchedule(datetime(2024, 12, 25, 9, 0))
        self.assertFalse(sched.triggered)
        sched.mark_triggered()
        self.assertTrue(sched.triggered)

    def test_run_at_property(self):
        run_at = datetime(2024, 12, 25, 9, 0)
        sched = OneTimeSchedule(run_at)
        self.assertEqual(sched.run_at, run_at)

    def test_description(self):
        run_at = datetime(2024, 12, 25, 9, 0)
        sched = OneTimeSchedule(run_at)
        self.assertIn("once at", sched.description())


if __name__ == "__main__":
    unittest.main()
