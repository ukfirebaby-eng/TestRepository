"""
Genesis Resolver — meta-node for robust pipeline error recovery.

Three sub-modules:

  ErrorClassifier   — Categorises job exceptions into actionable buckets.
  ViolationDetector — Detects runtime dependency and ordering violations.
  GenesisResolver   — Orchestrates recovery using the above two modules.

Usage::

    from scheduler.resolver import GenesisResolver
    from scheduler import Scheduler

    resolver = GenesisResolver()
    s = Scheduler(resolver=resolver)
    # The scheduler now applies intelligent recovery on every job failure.
"""

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Dict, List, Optional, Set

from .job import Job, JobStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------


class ErrorCategory(Enum):
    """Broad category of a job execution failure."""

    TRANSIENT = "transient"
    """Temporary condition (network blip, timeout) — safe to retry."""

    CONFIGURATION = "config"
    """Bad arguments or missing resource — retrying won't help."""

    RESOURCE = "resource"
    """OOM or disk-full — worth retrying after a longer delay."""

    DEPENDENCY = "dependency"
    """Upstream job failed before this job ran."""

    UNKNOWN = "unknown"
    """Uncategorised — fall back to standard scheduler defaults."""


class ErrorClassifier:  # @lat: [[error-classification]]
    """
    Maps a raw exception to an :class:`ErrorCategory`.

    The classification is intentionally conservative: when in doubt it
    returns ``UNKNOWN`` so the resolver falls back to standard retry logic.
    """

    _TRANSIENT_TYPES = (
        ConnectionError,
        TimeoutError,
        OSError,
    )
    _CONFIGURATION_TYPES = (
        ValueError,
        TypeError,
        AttributeError,
        KeyError,
    )
    _RESOURCE_TYPES = (MemoryError,)

    def classify(self, exc: Optional[Exception]) -> ErrorCategory:
        """Return the :class:`ErrorCategory` that best describes *exc*."""
        if exc is None:
            return ErrorCategory.UNKNOWN
        if isinstance(exc, self._TRANSIENT_TYPES):
            return ErrorCategory.TRANSIENT
        if isinstance(exc, self._RESOURCE_TYPES):
            return ErrorCategory.RESOURCE
        if isinstance(exc, self._CONFIGURATION_TYPES):
            return ErrorCategory.CONFIGURATION
        if isinstance(exc, RuntimeError) and "dependency" in str(exc).lower():
            return ErrorCategory.DEPENDENCY
        return ErrorCategory.UNKNOWN


# ---------------------------------------------------------------------------
# Violation detection
# ---------------------------------------------------------------------------


class ViolationType(Enum):
    """
    Runtime consistency violations in the job graph.

    Naming mirrors the Narrative State Engine taxonomy (V1–V5) but is
    applied to job-dependency relationships rather than story logic.
    """

    DEPENDENCY_FAILED = "V1"
    """A direct dependency is in FAILED state."""

    ORDERING = "V2"
    """Job started before one of its dependencies finished."""

    STALE_STATE = "V3"
    """Job is PENDING while a dependency has permanently failed."""

    ORPHANED = "V4"
    """Every dependency path is permanently failed; job can never run."""

    CONFLICT = "V5"
    """Job status contradicts its execution history."""


@dataclass
class Violation:
    """A single detected runtime violation."""

    type: ViolationType
    job_name: str
    description: str
    suggested_action: str


class ViolationDetector:  # @lat: [[violation-detection]]
    """
    Scans the live job registry for runtime inconsistencies.

    All five violation types are checked on each call; the resulting list
    can be filtered by ``job_name`` for targeted resolution.  This is a
    pure read — it never mutates any job state.
    """

    def detect(self, jobs: Dict[str, Job]) -> List[Violation]:
        """Inspect *jobs* and return every violation found."""
        violations: List[Violation] = []
        for name, job in jobs.items():
            violations.extend(self._check_v1(name, job, jobs))
            violations.extend(self._check_v2(name, job, jobs))
            violations.extend(self._check_v3(name, job, jobs))
            violations.extend(self._check_v4(name, job, jobs))
            violations.extend(self._check_v5(name, job))
        return violations

    # -- individual checkers -------------------------------------------------

    def _check_v1(
        self, name: str, job: Job, jobs: Dict[str, Job]
    ) -> List[Violation]:
        """V1 DEPENDENCY_FAILED: a direct dependency is in FAILED state."""
        result: List[Violation] = []
        for dep_name in job.dependencies:
            dep = jobs.get(dep_name)
            if dep and dep.status == JobStatus.FAILED:
                result.append(
                    Violation(
                        type=ViolationType.DEPENDENCY_FAILED,
                        job_name=name,
                        description=(
                            f"Dependency '{dep_name}' is in FAILED state; "
                            f"'{name}' cannot safely run."
                        ),
                        suggested_action=(
                            f"Resolve the failure in '{dep_name}' or remove "
                            f"the dependency before retrying '{name}'."
                        ),
                    )
                )
        return result

    def _check_v2(
        self, name: str, job: Job, jobs: Dict[str, Job]
    ) -> List[Violation]:
        """V2 ORDERING: job started before a dependency finished."""
        result: List[Violation] = []
        if not job.history:
            return result
        job_start = job.history[-1].started_at
        for dep_name in job.dependencies:
            dep = jobs.get(dep_name)
            if dep and dep.history:
                dep_finish = dep.history[-1].finished_at
                if dep_finish and job_start < dep_finish:
                    result.append(
                        Violation(
                            type=ViolationType.ORDERING,
                            job_name=name,
                            description=(
                                f"'{name}' started at {job_start.isoformat()} "
                                f"before '{dep_name}' finished at "
                                f"{dep_finish.isoformat()}."
                            ),
                            suggested_action=(
                                f"Verify that the scheduler enforces "
                                f"happens-before ordering between "
                                f"'{dep_name}' and '{name}'."
                            ),
                        )
                    )
        return result

    def _check_v3(
        self, name: str, job: Job, jobs: Dict[str, Job]
    ) -> List[Violation]:
        """V3 STALE_STATE: PENDING job treats a permanently-failed dep as valid."""
        result: List[Violation] = []
        if job.status != JobStatus.PENDING:
            return result
        for dep_name in job.dependencies:
            dep = jobs.get(dep_name)
            if dep and dep.status == JobStatus.FAILED and dep.max_retries == 0:
                result.append(
                    Violation(
                        type=ViolationType.STALE_STATE,
                        job_name=name,
                        description=(
                            f"'{name}' is PENDING but dependency '{dep_name}' "
                            f"has permanently failed (no retries configured)."
                        ),
                        suggested_action=(
                            f"Mark '{name}' as FAILED or remove its dependency "
                            f"on '{dep_name}' to unblock the pipeline."
                        ),
                    )
                )
        return result

    def _check_v4(
        self, name: str, job: Job, jobs: Dict[str, Job]
    ) -> List[Violation]:
        """V4 ORPHANED: every dependency path is permanently failed."""
        result: List[Violation] = []
        if not job.dependencies or job.status not in (JobStatus.PENDING,):
            return result

        def permanently_failed(dep_name: str, visited: Set[str]) -> bool:
            if dep_name in visited:
                return False  # cycle guard
            visited.add(dep_name)
            dep = jobs.get(dep_name)
            if dep is None:
                return False
            if dep.status == JobStatus.FAILED and dep.retry_count >= dep.max_retries:
                return True
            if dep.dependencies:
                return all(
                    permanently_failed(d, visited) for d in dep.dependencies
                )
            return False

        if all(permanently_failed(d, set()) for d in job.dependencies):
            result.append(
                Violation(
                    type=ViolationType.ORPHANED,
                    job_name=name,
                    description=(
                        f"All dependency paths for '{name}' are permanently "
                        f"failed; it can never run."
                    ),
                    suggested_action=(
                        f"Reset or remove the failed upstream jobs, or remove "
                        f"'{name}' from the scheduler."
                    ),
                )
            )
        return result

    def _check_v5(self, name: str, job: Job) -> List[Violation]:
        """V5 CONFLICT: status contradicts execution history."""
        result: List[Violation] = []
        if job.status == JobStatus.RUNNING and job.history:
            last = job.history[-1]
            if last.finished_at is not None:
                result.append(
                    Violation(
                        type=ViolationType.CONFLICT,
                        job_name=name,
                        description=(
                            f"'{name}' is marked RUNNING but its last history "
                            f"entry finished at {last.finished_at.isoformat()}."
                        ),
                        suggested_action=(
                            f"Reset '{name}' status to FAILED or PENDING to "
                            f"allow the scheduler to recover it."
                        ),
                    )
                )
        return result


# ---------------------------------------------------------------------------
# Recovery actions and results
# ---------------------------------------------------------------------------


class RecoveryAction(Enum):
    """The action the scheduler should take for a failed job."""

    RETRY_IMMEDIATE = "retry_immediate"
    """Retry using the job's configured ``retry_delay_seconds``."""

    RETRY_BACKOFF = "retry_backoff"
    """Retry after an exponentially extended delay."""

    SURGICAL_RETRY = "surgical_retry"
    """One additional attempt past ``max_retries``, with a longer delay."""

    SKIP = "skip"
    """Mark the job as FAILED and do not retry (blocking violation found)."""

    ESCALATE = "escalate"
    """Log prominently and mark FAILED — human intervention required."""


@dataclass
class ResolutionResult:
    """The resolver's verdict for a single failed job."""

    job_name: str
    action: RecoveryAction
    error_category: ErrorCategory
    violations: List[Violation]
    modified_retry_delay: Optional[float]
    """Concrete delay in seconds to use; ``None`` means use job default."""
    details: str


# ---------------------------------------------------------------------------
# Genesis Resolver
# ---------------------------------------------------------------------------


class GenesisResolver:  # @lat: [[genesis-resolver]]
    """
    Meta-node that orchestrates error recovery for failed jobs.

    Decision tree
    -------------
    1. **Blocking violation** (V1 DEPENDENCY_FAILED or V4 ORPHANED) →
       ``SKIP``: do not compound failures from broken dependencies.
    2. **Retries exhausted + transient error + no surgical retry yet** →
       ``SURGICAL_RETRY``: one extra attempt with a longer backoff delay.
    3. **Retries exhausted** (any other category) →
       ``ESCALATE``: needs human intervention.
    4. **Transient error** → ``RETRY_BACKOFF`` with exponential delay.
    5. **Configuration error** → ``ESCALATE``: retry cannot fix bad config.
    6. **Resource error** → ``RETRY_BACKOFF`` with extended delay.
    7. **Anything else** → ``RETRY_IMMEDIATE`` (if retries remain) or
       ``ESCALATE`` (if retries exhausted).

    Args:
        classifier: Error classifier; defaults to :class:`ErrorClassifier`.
        detector:   Violation detector; defaults to :class:`ViolationDetector`.
        surgical_backoff_multiplier: Factor applied to ``retry_delay_seconds``
            for the surgical retry attempt (default 4×).
    """

    def __init__(
        self,
        classifier: Optional[ErrorClassifier] = None,
        detector: Optional[ViolationDetector] = None,
        surgical_backoff_multiplier: float = 4.0,
    ) -> None:
        self._classifier = classifier or ErrorClassifier()
        self._detector = detector or ViolationDetector()
        self._surgical_backoff_multiplier = surgical_backoff_multiplier
        self._surgical_retried: Set[str] = set()

    def resolve(self, job: Job, jobs: Dict[str, Job]) -> ResolutionResult:
        """
        Analyse *job*'s last failure and return the recommended action.

        Args:
            job:  The job that just failed.
            jobs: The complete live job registry (read-only snapshot).

        Returns:
            A :class:`ResolutionResult` describing the action to take.
        """
        last_result = job.history[-1] if job.history else None
        exc = last_result.exception if last_result else None
        category = self._classifier.classify(exc)

        all_violations = self._detector.detect(jobs)
        job_violations = [v for v in all_violations if v.job_name == job.name]

        blocking_types = {ViolationType.DEPENDENCY_FAILED, ViolationType.ORPHANED}
        blocking = [v for v in job_violations if v.type in blocking_types]

        retries_exhausted = job.retry_count >= job.max_retries and job.max_retries > 0

        # --- decision tree --------------------------------------------------

        if blocking:
            action = RecoveryAction.SKIP
            delay = None
            details = (
                f"Skipping '{job.name}': blocking violation(s) — "
                + "; ".join(v.description for v in blocking)
            )

        elif retries_exhausted:
            if (
                category == ErrorCategory.TRANSIENT
                and job.name not in self._surgical_retried
            ):
                self._surgical_retried.add(job.name)
                action = RecoveryAction.SURGICAL_RETRY
                delay = job.retry_delay_seconds * self._surgical_backoff_multiplier
                details = (
                    f"Surgical retry for '{job.name}': transient error after "
                    f"{job.retry_count} normal retries; delay={delay:.1f}s."
                )
            else:
                action = RecoveryAction.ESCALATE
                delay = None
                details = (
                    f"Escalating '{job.name}': retries exhausted "
                    f"(category={category.value}). Manual intervention required."
                )

        elif category == ErrorCategory.TRANSIENT:
            action = RecoveryAction.RETRY_BACKOFF
            delay = job.retry_delay_seconds * (2 ** max(job.retry_count, 0))
            details = (
                f"Backoff retry for '{job.name}': transient error, "
                f"attempt {job.retry_count + 1}; delay={delay:.1f}s."
            )

        elif category == ErrorCategory.RESOURCE:
            action = RecoveryAction.RETRY_BACKOFF
            delay = job.retry_delay_seconds * self._surgical_backoff_multiplier
            details = (
                f"Backoff retry for '{job.name}': resource error; "
                f"delay={delay:.1f}s."
            )

        elif category == ErrorCategory.CONFIGURATION:
            action = RecoveryAction.ESCALATE
            delay = None
            details = (
                f"Escalating '{job.name}': configuration error — "
                f"retrying will not fix this. Check job arguments/environment."
            )

        else:
            # UNKNOWN / DEPENDENCY — standard retry if budget remains
            if job.retry_count < job.max_retries:
                action = RecoveryAction.RETRY_IMMEDIATE
                delay = job.retry_delay_seconds
            else:
                action = RecoveryAction.ESCALATE
                delay = None
            details = (
                f"Standard handling for '{job.name}': "
                f"category={category.value}, action={action.value}."
            )

        log_fn = (
            logger.warning
            if action in (RecoveryAction.ESCALATE, RecoveryAction.SKIP)
            else logger.info
        )
        log_fn("[GenesisResolver] %s", details)

        return ResolutionResult(
            job_name=job.name,
            action=action,
            error_category=category,
            violations=job_violations,
            modified_retry_delay=delay,
            details=details,
        )
