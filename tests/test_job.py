"""Tests for the Job class and JobStatus."""

import unittest
from datetime import datetime, timedelta

from scheduler.job import Job, JobStatus
from scheduler.schedules import IntervalSchedule, OneTimeSchedule


def _make_job(name="test", func=None, schedule=None, **kwargs):
    if func is None:
        func = lambda: None
    if schedule is None:
        schedule = IntervalSchedule(seconds=60)
    return Job(name, func, schedule, **kwargs)


class TestJobDefaults(unittest.TestCase):

    def test_initial_status_is_pending(self):
        job = _make_job()
        self.assertEqual(job.status, JobStatus.PENDING)

    def test_initial_last_run_is_none(self):
        job = _make_job()
        self.assertIsNone(job.last_run)

    def test_initial_retry_count_is_zero(self):
        job = _make_job()
        self.assertEqual(job.retry_count, 0)

    def test_empty_history(self):
        job = _make_job()
        self.assertEqual(job.history, [])

    def test_empty_dependencies(self):
        job = _make_job()
        self.assertEqual(job.dependencies, [])

    def test_repr_contains_name(self):
        job = _make_job(name="my_job")
        self.assertIn("my_job", repr(job))


class TestJobExecution(unittest.TestCase):

    def test_successful_run_sets_completed(self):
        results = []
        job = _make_job(func=lambda: results.append(1))
        result = job.run()
        self.assertTrue(result.success)
        self.assertEqual(results, [1])

    def test_failed_run_captures_exception(self):
        def fail():
            raise ValueError("boom")

        job = _make_job(func=fail)
        result = job.run()
        self.assertFalse(result.success)
        self.assertIsInstance(result.exception, ValueError)
        self.assertEqual(str(result.exception), "boom")

    def test_run_stores_result_in_history(self):
        job = _make_job(func=lambda: 42)
        job.run()
        self.assertEqual(len(job.history), 1)
        self.assertTrue(job.history[0].success)
        self.assertEqual(job.history[0].return_value, 42)

    def test_run_sets_last_run(self):
        before = datetime.now()
        job = _make_job()
        job.run()
        after = datetime.now()
        self.assertIsNotNone(job.last_run)
        self.assertGreaterEqual(job.last_run, before)
        self.assertLessEqual(job.last_run, after)

    def test_run_accepts_args(self):
        received = []
        job = _make_job(
            func=lambda x, y: received.extend([x, y]),
            args=(1, 2),
        )
        job.run()
        self.assertEqual(received, [1, 2])

    def test_run_accepts_kwargs(self):
        received = {}
        job = _make_job(
            func=lambda k=None: received.update({"k": k}),
            kwargs={"k": "value"},
        )
        job.run()
        self.assertEqual(received, {"k": "value"})


class TestJobStatusTransitions(unittest.TestCase):

    def test_mark_completed(self):
        job = _make_job()
        job.mark_completed()
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.retry_count, 0)

    def test_mark_failed(self):
        job = _make_job()
        job.mark_failed()
        self.assertEqual(job.status, JobStatus.FAILED)

    def test_schedule_retry(self):
        job = _make_job()
        retry_at = datetime(2024, 1, 1, 12, 0)
        job.schedule_retry(retry_at)
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertEqual(job.retry_count, 1)
        self.assertEqual(job.next_run, retry_at)

    def test_multiple_retries_increment_count(self):
        job = _make_job()
        job.schedule_retry(datetime.now() + timedelta(seconds=5))
        job.schedule_retry(datetime.now() + timedelta(seconds=5))
        self.assertEqual(job.retry_count, 2)


class TestJobIsReady(unittest.TestCase):

    def test_ready_when_conditions_met(self):
        job = _make_job()
        past = datetime(2024, 1, 1, 0, 0)
        job.next_run = past
        self.assertTrue(job.is_ready(datetime.now(), set()))

    def test_not_ready_if_running(self):
        job = _make_job()
        job.status = JobStatus.RUNNING
        job.next_run = datetime(2024, 1, 1, 0, 0)
        self.assertFalse(job.is_ready(datetime.now(), set()))

    def test_not_ready_if_next_run_in_future(self):
        job = _make_job()
        job.next_run = datetime.now() + timedelta(hours=1)
        self.assertFalse(job.is_ready(datetime.now(), set()))

    def test_not_ready_if_next_run_is_none(self):
        job = _make_job()
        job.next_run = None
        self.assertFalse(job.is_ready(datetime.now(), set()))

    def test_not_ready_if_dependency_not_completed(self):
        job = _make_job(dependencies=["dep_job"])
        job.next_run = datetime(2024, 1, 1, 0, 0)
        self.assertFalse(job.is_ready(datetime.now(), set()))

    def test_ready_when_dependency_completed(self):
        job = _make_job(dependencies=["dep_job"])
        job.next_run = datetime(2024, 1, 1, 0, 0)
        self.assertTrue(job.is_ready(datetime.now(), {"dep_job"}))

    def test_not_ready_if_expired(self):
        job = _make_job()
        job.status = JobStatus.EXPIRED
        job.next_run = datetime(2024, 1, 1, 0, 0)
        self.assertFalse(job.is_ready(datetime.now(), set()))


class TestJobComputeNextRun(unittest.TestCase):

    def test_interval_schedule_returns_datetime(self):
        job = _make_job(schedule=IntervalSchedule(seconds=30))
        nxt = job.compute_next_run(datetime(2024, 1, 1, 10, 0, 0))
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt, datetime(2024, 1, 1, 10, 0, 30))
        self.assertEqual(job.next_run, nxt)

    def test_one_time_schedule_returns_none_after_trigger(self):
        run_at = datetime(2024, 12, 25, 9, 0)
        job = _make_job(schedule=OneTimeSchedule(run_at))
        # First call triggers it
        nxt = job.compute_next_run(datetime(2024, 12, 24, 0, 0))
        self.assertIsNone(nxt)
        self.assertEqual(job.status, JobStatus.EXPIRED)


if __name__ == "__main__":
    unittest.main()
