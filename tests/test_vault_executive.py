import json
import pytest
from core.vault import HybridVault


@pytest.fixture
def vault(tmp_path):
    v = HybridVault(tenant_id="test_exec", base_dir=str(tmp_path))
    yield v
    v.conn.close()


def _sample_report():
    return {
        "overall_assessment": "Moderate Risk",
        "generated_at": "2026-03-25T12:00:00Z",
        "summary_narrative": "Three issues detected.",
        "business_impact": "Risk of delay.",
        "issues": [{"severity": "high", "title": "Test", "plain_english": "Test.", "solution": "Fix it.", "source_nodes": []}],
        "coverage_verified": True,
        "coverage_warning": None,
    }


class TestGetExecutiveSummary:
    def test_returns_none_when_no_cache(self, vault):
        vault.insert_document("doc_1", "test.pdf")
        assert vault.get_executive_summary("doc_1") is None

    def test_returns_none_for_unknown_document(self, vault):
        assert vault.get_executive_summary("doc_missing") is None


class TestSaveExecutiveSummary:
    def test_save_and_retrieve(self, vault):
        vault.insert_document("doc_1", "test.pdf")
        report = _sample_report()
        vault.save_executive_summary("doc_1", report, "gpt-4o")
        result = vault.get_executive_summary("doc_1")
        assert result is not None
        assert result["overall_assessment"] == "Moderate Risk"

    def test_returned_dict_matches_saved(self, vault):
        vault.insert_document("doc_1", "test.pdf")
        report = _sample_report()
        vault.save_executive_summary("doc_1", report, "gpt-4o")
        result = vault.get_executive_summary("doc_1")
        assert result["issues"][0]["title"] == "Test"
        assert result["coverage_verified"] is True

    def test_overwrite_replaces_existing(self, vault):
        vault.insert_document("doc_1", "test.pdf")
        vault.save_executive_summary("doc_1", _sample_report(), "gpt-4o")
        updated = _sample_report()
        updated["overall_assessment"] = "High Risk"
        vault.save_executive_summary("doc_1", updated, "gpt-4o")
        result = vault.get_executive_summary("doc_1")
        assert result["overall_assessment"] == "High Risk"


class TestDeleteExecutiveSummary:
    def test_delete_removes_cache(self, vault):
        vault.insert_document("doc_1", "test.pdf")
        vault.save_executive_summary("doc_1", _sample_report(), "gpt-4o")
        vault.delete_executive_summary("doc_1")
        assert vault.get_executive_summary("doc_1") is None

    def test_delete_is_idempotent(self, vault):
        vault.insert_document("doc_1", "test.pdf")
        # No cache row exists — should not raise
        vault.delete_executive_summary("doc_1")
        vault.delete_executive_summary("doc_1")  # second call also safe
