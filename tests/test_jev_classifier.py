"""Tests for the Jev-backed error classifier (the TypeSafe client is mocked)."""

import unittest
from types import SimpleNamespace

from scheduler import GenesisResolver
from scheduler.jev_classifier import JevErrorClassifier
from scheduler.resolver import ErrorCategory, RecoveryAction

from tests.test_resolver import _failed_job


class _FakeClient:
    """Stands in for ``typesafe_sdk.TypeSafeClient``."""

    def __init__(self, choice="transient", confidence=0.9, error=None):
        self.choice = choice
        self.confidence = confidence
        self.error = error
        self.calls = []

    def system_one(self, state, questions, **kwargs):
        self.calls.append({"state": state, "questions": questions, **kwargs})
        if self.error is not None:
            raise self.error
        answer = SimpleNamespace(choice=self.choice, confidence=self.confidence)
        return SimpleNamespace(choices={"category": answer})


class _CustomError(Exception):
    pass


class TestJevErrorClassifier(unittest.TestCase):

    def test_rule_based_categories_skip_jev(self):
        client = _FakeClient()
        classifier = JevErrorClassifier(client=client)
        self.assertEqual(
            classifier.classify(ConnectionError("x")), ErrorCategory.TRANSIENT
        )
        self.assertEqual(
            classifier.classify(ValueError("x")), ErrorCategory.CONFIGURATION
        )
        self.assertEqual(classifier.classify(None), ErrorCategory.UNKNOWN)
        self.assertEqual(client.calls, [])

    def test_unknown_error_uses_jev_answer(self):
        client = _FakeClient(choice="resource", confidence=0.95)
        classifier = JevErrorClassifier(client=client)
        exc = _CustomError("quota exceeded for bucket")
        self.assertEqual(classifier.classify(exc), ErrorCategory.RESOURCE)

        call = client.calls[0]
        self.assertEqual(call["state"]["exception_type"], "_CustomError")
        self.assertEqual(call["state"]["message"], "quota exceeded for bucket")
        question = call["questions"]["category"]
        self.assertEqual(question["type"], "choice")
        self.assertEqual(
            set(question["criteria"]), {c.value for c in ErrorCategory}
        )
        self.assertEqual(call["timeout"], 2.0)

    def test_low_confidence_falls_back_to_unknown(self):
        client = _FakeClient(choice="transient", confidence=0.4)
        classifier = JevErrorClassifier(client=client, min_confidence=0.7)
        self.assertEqual(
            classifier.classify(_CustomError("?")), ErrorCategory.UNKNOWN
        )

    def test_api_error_falls_back_to_unknown(self):
        client = _FakeClient(error=RuntimeError("503 from API"))
        classifier = JevErrorClassifier(client=client)
        with self.assertLogs("scheduler.jev_classifier", level="WARNING"):
            result = classifier.classify(_CustomError("?"))
        self.assertEqual(result, ErrorCategory.UNKNOWN)

    def test_unexpected_label_falls_back_to_unknown(self):
        client = _FakeClient(choice="not-a-category")
        classifier = JevErrorClassifier(client=client)
        with self.assertLogs("scheduler.jev_classifier", level="WARNING"):
            result = classifier.classify(_CustomError("?"))
        self.assertEqual(result, ErrorCategory.UNKNOWN)

    def test_resolver_acts_on_jev_category(self):
        client = _FakeClient(choice="config", confidence=0.9)
        resolver = GenesisResolver(classifier=JevErrorClassifier(client=client))
        job = _failed_job(exc=_CustomError("missing S3_BUCKET"), max_retries=3)
        result = resolver.resolve(job, {job.name: job})
        self.assertEqual(result.error_category, ErrorCategory.CONFIGURATION)
        self.assertEqual(result.action, RecoveryAction.ESCALATE)


if __name__ == "__main__":
    unittest.main()
