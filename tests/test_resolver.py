"""Tests for the Genesis Resolver sub-modules and Scheduler integration."""

import time
import unittest
from datetime import datetime, timedelta

from scheduler import (
    GenesisResolver,
    Job,
    JobStatus,
    Scheduler,
)
from scheduler.resolver import (
    ErrorCategory,
    ErrorClassifier,
    RecoveryAction,
    ResolutionResult,
    Violation,
    ViolationDetector,
    ViolationType,
)
from scheduler.schedules import IntervalSchedule, OneTimeSchedule


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job(name="job", func=None, schedule=None, **kwargs):
    if func is None:
        func = lambda: None
    if schedule is None:
        schedule = IntervalSchedule(seconds=60)
    return Job(name, func, schedule, **kwargs)


def _failed_job(name="job", exc=None, retry_count=0, max_retries=0, **kwargs):
    """Create a job whose last history entry is a failure."""
    if exc is None:
        exc = RuntimeError("boom")
    job = _make_job(name, max_retries=max_retries, **kwargs)
    result = _fake_result(job.name, exc=exc)
    job.history.append(result)
    job.status = JobStatus.FAILED
    job.retry_count = retry_count
    return job


def _fake_result(job_name, success=False, exc=None):
    from scheduler.job import JobResult

    now = datetime.now()
    return JobResult(
        job_name=job_name,
        started_at=now - timedelta(seconds=1),
        finished_at=now,
        success=success,
        exception=exc,
    )


# ---------------------------------------------------------------------------
# ErrorClassifier
# ---------------------------------------------------------------------------


class TestErrorClassifier(unittest.TestCase):

    def setUp(self):
        self.clf = ErrorClassifier()

    def test_none_returns_unknown(self):
        self.assertEqual(self.clf.classify(None), ErrorCategory.UNKNOWN)

    def test_connection_error_is_transient(self):
        self.assertEqual(
            self.clf.classify(ConnectionError("refused")),
            ErrorCategory.TRANSIENT,
        )

    def test_timeout_error_is_transient(self):
        self.assertEqual(
            self.clf.classify(TimeoutError()),
            ErrorCategory.TRANSIENT,
        )

    def test_os_error_is_transient(self):
        self.assertEqual(self.clf.classify(OSError("io error")), ErrorCategory.TRANSIENT)

    def test_value_error_is_configuration(self):
        self.assertEqual(
            self.clf.classify(ValueError("bad arg")),
            ErrorCategory.CONFIGURATION,
        )

    def test_type_error_is_configuration(self):
        self.assertEqual(
            self.clf.classify(TypeError("wrong type")),
            ErrorCategory.CONFIGURATION,
        )

    def test_attribute_error_is_configuration(self):
        self.assertEqual(
            self.clf.classify(AttributeError("missing attr")),
            ErrorCategory.CONFIGURATION,
        )

    def test_key_error_is_configuration(self):
        self.assertEqual(self.clf.classify(KeyError("x")), ErrorCategory.CONFIGURATION)

    def test_memory_error_is_resource(self):
        self.assertEqual(
            self.clf.classify(MemoryError()),
            ErrorCategory.RESOURCE,
        )

    def test_runtime_dependency_message_is_dependency(self):
        self.assertEqual(
            self.clf.classify(RuntimeError("dependency failed")),
            ErrorCategory.DEPENDENCY,
        )

    def test_plain_runtime_error_is_unknown(self):
        self.assertEqual(
            self.clf.classify(RuntimeError("something else")),
            ErrorCategory.UNKNOWN,
        )


# ---------------------------------------------------------------------------
# ViolationDetector
# ---------------------------------------------------------------------------


class TestViolationDetector(unittest.TestCase):

    def setUp(self):
        self.det = ViolationDetector()

    def _jobs(self, *jobs):
        return {j.name: j for j in jobs}

    # V1 ----------------------------------------------------------------

    def test_v1_detects_failed_dependency(self):
        dep = _make_job("dep")
        dep.status = JobStatus.FAILED
        child = _make_job("child", dependencies=["dep"])
        violations = self.det.detect(self._jobs(dep, child))
        v1 = [v for v in violations if v.type == ViolationType.DEPENDENCY_FAILED]
        self.assertEqual(len(v1), 1)
        self.assertEqual(v1[0].job_name, "child")

    def test_v1_no_violation_when_dep_completed(self):
        dep = _make_job("dep")
        dep.status = JobStatus.COMPLETED
        child = _make_job("child", dependencies=["dep"])
        violations = self.det.detect(self._jobs(dep, child))
        v1 = [v for v in violations if v.type == ViolationType.DEPENDENCY_FAILED]
        self.assertEqual(len(v1), 0)

    # V2 ----------------------------------------------------------------

    def test_v2_detects_ordering_violation(self):
        dep = _make_job("dep")
        child = _make_job("child", dependencies=["dep"])

        # Child started at T=0, dep finished at T=1 → ordering violation
        t0 = datetime(2024, 1, 1, 12, 0, 0)
        t1 = t0 + timedelta(seconds=1)

        from scheduler.job import JobResult

        dep.history.append(
            JobResult("dep", t0, t1, success=True)
        )
        child.history.append(
            JobResult("child", t0, t0 + timedelta(seconds=2), success=False)
        )

        violations = self.det.detect(self._jobs(dep, child))
        v2 = [v for v in violations if v.type == ViolationType.ORDERING]
        self.assertEqual(len(v2), 1)
        self.assertEqual(v2[0].job_name, "child")

    def test_v2_no_violation_when_order_correct(self):
        dep = _make_job("dep")
        child = _make_job("child", dependencies=["dep"])

        t0 = datetime(2024, 1, 1, 12, 0, 0)

        from scheduler.job import JobResult

        dep.history.append(JobResult("dep", t0, t0 + timedelta(seconds=1), success=True))
        # Child started after dep finished
        child.history.append(
            JobResult(
                "child",
                t0 + timedelta(seconds=2),
                t0 + timedelta(seconds=3),
                success=False,
            )
        )

        violations = self.det.detect(self._jobs(dep, child))
        v2 = [v for v in violations if v.type == ViolationType.ORDERING]
        self.assertEqual(len(v2), 0)

    # V3 ----------------------------------------------------------------

    def test_v3_detects_stale_pending_job(self):
        dep = _make_job("dep", max_retries=0)
        dep.status = JobStatus.FAILED

        child = _make_job("child", dependencies=["dep"])
        child.status = JobStatus.PENDING

        violations = self.det.detect(self._jobs(dep, child))
        v3 = [v for v in violations if v.type == ViolationType.STALE_STATE]
        self.assertEqual(len(v3), 1)

    def test_v3_not_triggered_when_dep_has_retries(self):
        dep = _make_job("dep", max_retries=2)
        dep.status = JobStatus.FAILED

        child = _make_job("child", dependencies=["dep"])
        child.status = JobStatus.PENDING

        violations = self.det.detect(self._jobs(dep, child))
        v3 = [v for v in violations if v.type == ViolationType.STALE_STATE]
        self.assertEqual(len(v3), 0)

    # V4 ----------------------------------------------------------------

    def test_v4_detects_orphaned_job(self):
        dep = _make_job("dep", max_retries=0)
        dep.status = JobStatus.FAILED
        dep.retry_count = 0

        child = _make_job("child", dependencies=["dep"])
        child.status = JobStatus.PENDING

        violations = self.det.detect(self._jobs(dep, child))
        v4 = [v for v in violations if v.type == ViolationType.ORPHANED]
        self.assertEqual(len(v4), 1)
        self.assertEqual(v4[0].job_name, "child")

    def test_v4_not_triggered_when_dep_can_retry(self):
        dep = _make_job("dep", max_retries=3)
        dep.status = JobStatus.FAILED
        dep.retry_count = 1  # still has retries left

        child = _make_job("child", dependencies=["dep"])
        child.status = JobStatus.PENDING

        violations = self.det.detect(self._jobs(dep, child))
        v4 = [v for v in violations if v.type == ViolationType.ORPHANED]
        self.assertEqual(len(v4), 0)

    # V5 ----------------------------------------------------------------

    def test_v5_detects_running_job_with_finished_history(self):
        from scheduler.job import JobResult

        job = _make_job("j")
        job.status = JobStatus.RUNNING
        t = datetime(2024, 6, 1, 10, 0)
        job.history.append(JobResult("j", t, t + timedelta(seconds=1), success=False))

        violations = self.det.detect({"j": job})
        v5 = [v for v in violations if v.type == ViolationType.CONFLICT]
        self.assertEqual(len(v5), 1)

    def test_v5_no_violation_when_running_with_no_history(self):
        job = _make_job("j")
        job.status = JobStatus.RUNNING

        violations = self.det.detect({"j": job})
        v5 = [v for v in violations if v.type == ViolationType.CONFLICT]
        self.assertEqual(len(v5), 0)

    # No violations for clean state -------------------------------------

    def test_no_violations_for_clean_graph(self):
        dep = _make_job("dep")
        dep.status = JobStatus.COMPLETED

        child = _make_job("child", dependencies=["dep"])
        child.status = JobStatus.PENDING
        child.next_run = datetime.now() + timedelta(seconds=30)

        violations = self.det.detect({"dep": dep, "child": child})
        self.assertEqual(violations, [])


# ---------------------------------------------------------------------------
# GenesisResolver
# ---------------------------------------------------------------------------


class TestGenesisResolver(unittest.TestCase):

    def setUp(self):
        self.resolver = GenesisResolver()

    def _registry(self, *jobs):
        return {j.name: j for j in jobs}

    # --- blocking violations -----------------------------------------------

    def test_skip_when_dependency_failed(self):
        dep = _make_job("dep")
        dep.status = JobStatus.FAILED

        child = _failed_job("child", dependencies=["dep"])

        result = self.resolver.resolve(child, self._registry(dep, child))
        self.assertEqual(result.action, RecoveryAction.SKIP)
        self.assertIn(ViolationType.DEPENDENCY_FAILED, [v.type for v in result.violations])

    def test_skip_when_orphaned(self):
        dep = _make_job("dep", max_retries=0)
        dep.status = JobStatus.FAILED
        dep.retry_count = 0

        child = _failed_job("child", dependencies=["dep"])
        child.status = JobStatus.PENDING

        result = self.resolver.resolve(child, self._registry(dep, child))
        self.assertEqual(result.action, RecoveryAction.SKIP)

    # --- transient errors ---------------------------------------------------

    def test_backoff_retry_for_transient_error(self):
        job = _failed_job("j", exc=ConnectionError("refused"), max_retries=3)
        result = self.resolver.resolve(job, self._registry(job))
        self.assertEqual(result.action, RecoveryAction.RETRY_BACKOFF)
        self.assertEqual(result.error_category, ErrorCategory.TRANSIENT)
        self.assertIsNotNone(result.modified_retry_delay)

    def test_surgical_retry_after_retries_exhausted(self):
        job = _failed_job(
            "j",
            exc=ConnectionError("refused"),
            max_retries=2,
            retry_count=2,
        )
        result = self.resolver.resolve(job, self._registry(job))
        self.assertEqual(result.action, RecoveryAction.SURGICAL_RETRY)
        self.assertIsNotNone(result.modified_retry_delay)

    def test_surgical_retry_only_fires_once(self):
        resolver = GenesisResolver()
        job = _failed_job(
            "j",
            exc=ConnectionError("refused"),
            max_retries=2,
            retry_count=2,
        )
        r1 = resolver.resolve(job, self._registry(job))
        self.assertEqual(r1.action, RecoveryAction.SURGICAL_RETRY)
        # Second call for same job must escalate
        r2 = resolver.resolve(job, self._registry(job))
        self.assertEqual(r2.action, RecoveryAction.ESCALATE)

    # --- configuration errors -----------------------------------------------

    def test_escalate_for_configuration_error(self):
        job = _failed_job("j", exc=ValueError("bad arg"), max_retries=3)
        result = self.resolver.resolve(job, self._registry(job))
        self.assertEqual(result.action, RecoveryAction.ESCALATE)
        self.assertEqual(result.error_category, ErrorCategory.CONFIGURATION)

    # --- resource errors ----------------------------------------------------

    def test_backoff_retry_for_resource_error(self):
        job = _failed_job("j", exc=MemoryError(), max_retries=3)
        result = self.resolver.resolve(job, self._registry(job))
        self.assertEqual(result.action, RecoveryAction.RETRY_BACKOFF)
        self.assertEqual(result.error_category, ErrorCategory.RESOURCE)

    # --- unknown errors -----------------------------------------------------

    def test_retry_immediate_for_unknown_error_with_budget(self):
        job = _failed_job("j", exc=RuntimeError("weird"), max_retries=3)
        result = self.resolver.resolve(job, self._registry(job))
        self.assertEqual(result.action, RecoveryAction.RETRY_IMMEDIATE)

    def test_escalate_for_unknown_error_no_budget(self):
        job = _failed_job("j", exc=RuntimeError("weird"), max_retries=0)
        result = self.resolver.resolve(job, self._registry(job))
        self.assertEqual(result.action, RecoveryAction.ESCALATE)

    # --- exponential backoff delay ------------------------------------------

    def test_backoff_delay_grows_with_retry_count(self):
        resolver = GenesisResolver()
        base = 5.0

        job0 = _failed_job("j0", exc=ConnectionError(), retry_count=0, max_retries=5,
                            retry_delay_seconds=base)
        r0 = resolver.resolve(job0, self._registry(job0))

        job1 = _failed_job("j1", exc=ConnectionError(), retry_count=1, max_retries=5,
                            retry_delay_seconds=base)
        r1 = resolver.resolve(job1, self._registry(job1))

        self.assertIsNotNone(r0.modified_retry_delay)
        self.assertIsNotNone(r1.modified_retry_delay)
        self.assertGreater(r1.modified_retry_delay, r0.modified_retry_delay)

    # --- surgical backoff multiplier ----------------------------------------

    def test_custom_surgical_backoff_multiplier(self):
        resolver = GenesisResolver(surgical_backoff_multiplier=10.0)
        job = _failed_job("j", exc=ConnectionError(), max_retries=1, retry_count=1,
                          retry_delay_seconds=2.0)
        result = resolver.resolve(job, self._registry(job))
        self.assertEqual(result.action, RecoveryAction.SURGICAL_RETRY)
        self.assertAlmostEqual(result.modified_retry_delay, 20.0)

    # --- result fields -------------------------------------------------------

    def test_resolution_result_contains_expected_fields(self):
        job = _failed_job("j", exc=ConnectionError())
        result = self.resolver.resolve(job, self._registry(job))
        self.assertIsInstance(result, ResolutionResult)
        self.assertEqual(result.job_name, "j")
        self.assertIsInstance(result.action, RecoveryAction)
        self.assertIsInstance(result.error_category, ErrorCategory)
        self.assertIsInstance(result.violations, list)
        self.assertIsInstance(result.details, str)


# ---------------------------------------------------------------------------
# Scheduler + GenesisResolver integration
# ---------------------------------------------------------------------------


class TestSchedulerWithResolver(unittest.TestCase):
    """Integration tests verifying that the Scheduler acts on resolver verdicts."""

    def test_resolver_triggers_retry_for_transient_failure(self):
        attempts = []

        def flaky():
            attempts.append(1)
            if len(attempts) < 2:
                raise ConnectionError("transient")

        resolver = GenesisResolver()
        s = Scheduler(tick_interval=0.02, resolver=resolver)
        run_at = datetime.now() + timedelta(milliseconds=50)
        job = Job(
            "flaky",
            flaky,
            OneTimeSchedule(run_at),
            max_retries=3,
            retry_delay_seconds=0.05,
        )
        s.add_job(job)
        s.start()
        time.sleep(1.0)
        s.stop()

        self.assertGreaterEqual(len(attempts), 2)

    def test_resolver_skip_does_not_retry_on_dependency_failure(self):
        dep_calls = []
        child_calls = []

        def dep_func():
            dep_calls.append(1)
            raise RuntimeError("dep always fails")

        def child_func():
            child_calls.append(1)

        resolver = GenesisResolver()
        s = Scheduler(tick_interval=0.02, resolver=resolver)
        run_at = datetime.now() + timedelta(milliseconds=50)

        s.add_job(Job("dep", dep_func, OneTimeSchedule(run_at), max_retries=0))
        s.add_job(
            Job(
                "child",
                child_func,
                OneTimeSchedule(run_at),
                dependencies=["dep"],
                max_retries=3,
            )
        )
        s.start()
        time.sleep(0.8)
        s.stop()

        # dep failed; child was blocked and should not have run
        self.assertEqual(dep_calls, [1])
        self.assertEqual(child_calls, [])

    def test_scheduler_works_without_resolver(self):
        """Verify the default (no-resolver) path still works correctly."""
        attempts = []

        def flaky():
            attempts.append(1)
            if len(attempts) < 2:
                raise RuntimeError("first fail")

        s = Scheduler(tick_interval=0.02)
        run_at = datetime.now() + timedelta(milliseconds=50)
        job = Job(
            "flaky",
            flaky,
            OneTimeSchedule(run_at),
            max_retries=2,
            retry_delay_seconds=0.05,
        )
        s.add_job(job)
        s.start()
        time.sleep(0.8)
        s.stop()
        self.assertGreaterEqual(len(attempts), 2)


if __name__ == "__main__":
    unittest.main()
