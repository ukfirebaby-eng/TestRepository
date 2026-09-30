"""
Jev-backed error classification for the Genesis Resolver.

:class:`JevErrorClassifier` keeps the rule-based :class:`ErrorClassifier` as
its first pass and only asks TypeSafe AI's Jev model about exceptions the
rules leave as ``UNKNOWN``.  Any API failure or low-confidence answer falls
back to ``UNKNOWN``, so recovery behaves exactly as it would without Jev.

Requires the optional ``typesafe-sdk`` package (``pip install typesafe-sdk``)
and a ``TYPESAFE_API_KEY`` environment variable, unless a client is supplied.

Usage::

    from scheduler import GenesisResolver, Scheduler
    from scheduler.jev_classifier import JevErrorClassifier

    resolver = GenesisResolver(classifier=JevErrorClassifier())
    s = Scheduler(resolver=resolver)
"""

import logging
import traceback
from typing import Any, Optional

from .resolver import ErrorCategory, ErrorClassifier

logger = logging.getLogger(__name__)

_CATEGORY_DESCRIPTIONS = {
    ErrorCategory.TRANSIENT.value: (
        "Temporary condition such as a network blip, timeout or unavailable "
        "service; retrying is likely to succeed."
    ),
    ErrorCategory.CONFIGURATION.value: (
        "Bad arguments, invalid settings, missing credentials or a missing "
        "resource; retrying will not help."
    ),
    ErrorCategory.RESOURCE.value: (
        "Exhausted resources such as memory, disk space or quota; retrying "
        "may succeed after a longer delay."
    ),
    ErrorCategory.DEPENDENCY.value: (
        "An upstream job or prerequisite step failed before this job ran."
    ),
    ErrorCategory.UNKNOWN.value: "None of the other categories clearly apply.",
}


class JevErrorClassifier(ErrorClassifier):
    """
    Rule-based classification with Jev as a fallback for unknown errors.

    Args:
        client: A ``typesafe_sdk.TypeSafeClient`` (or compatible object with a
            ``system_one`` method).  Created lazily from the environment when
            omitted.
        min_confidence: Jev answers below this confidence are discarded and
            the error stays ``UNKNOWN``.
        timeout: Per-call timeout in seconds, kept short because
            classification runs on the scheduler's failure path.
    """

    def __init__(
        self,
        client: Optional[Any] = None,
        min_confidence: float = 0.7,
        timeout: float = 2.0,
    ) -> None:
        self._client = client
        self._min_confidence = min_confidence
        self._timeout = timeout

    def classify(self, exc: Optional[Exception]) -> ErrorCategory:
        """Return the rule-based category, consulting Jev only for ``UNKNOWN``."""
        category = super().classify(exc)
        if category is not ErrorCategory.UNKNOWN or exc is None:
            return category
        try:
            return self._classify_with_jev(exc)
        except Exception:  # never let the classifier break recovery
            logger.warning(
                "[JevErrorClassifier] Jev classification failed; using UNKNOWN",
                exc_info=True,
            )
            return ErrorCategory.UNKNOWN

    def _classify_with_jev(self, exc: Exception) -> ErrorCategory:
        response = self._get_client().system_one(
            state={
                "exception_type": type(exc).__name__,
                "message": str(exc),
                "traceback": "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                )[-2000:],
            },
            questions={
                "category": {
                    "type": "choice",
                    "instructions": (
                        "Classify this scheduled job's failure so the scheduler "
                        "can decide whether and when to retry it."
                    ),
                    "criteria": _CATEGORY_DESCRIPTIONS,
                },
            },
            timeout=self._timeout,
        )
        answer = response.choices["category"]
        if answer.confidence < self._min_confidence:
            logger.info(
                "[JevErrorClassifier] Low confidence %.2f for %r; using UNKNOWN",
                answer.confidence,
                answer.choice,
            )
            return ErrorCategory.UNKNOWN
        return ErrorCategory(answer.choice)

    def _get_client(self) -> Any:
        if self._client is None:
            from typesafe_sdk import TypeSafeClient

            self._client = TypeSafeClient()
        return self._client
