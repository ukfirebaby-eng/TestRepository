import pytest
from core.vault import HybridVault


@pytest.fixture
def vault(tmp_path):
    v = HybridVault(tenant_id="test_narrative", base_dir=str(tmp_path))
    yield v
    v.conn.close()


def _sample_report():
    return {
        "title": "Narrative Report",
        "sections": ["intro", "analysis"],
        "risk_score": 7,
    }


def test_save_and_get_narrative_report(vault):
    vault.insert_document("doc_1", "test.pdf")
    report = _sample_report()
    vault.save_narrative_report("doc_1", report, "claude-3-5-sonnet")
    result = vault.get_narrative_report("doc_1")
    assert result is not None
    assert result == report


def test_get_returns_none_when_absent(vault):
    assert vault.get_narrative_report("doc_missing") is None


def test_save_upserts_on_conflict(vault):
    vault.insert_document("doc_1", "test.pdf")
    vault.save_narrative_report("doc_1", _sample_report(), "claude-3-5-sonnet")
    updated = {"title": "Updated Report", "sections": [], "risk_score": 2}
    vault.save_narrative_report("doc_1", updated, "claude-3-5-sonnet")
    result = vault.get_narrative_report("doc_1")
    assert result["title"] == "Updated Report"
    assert result["risk_score"] == 2


def test_delete_removes_row(vault):
    vault.insert_document("doc_1", "test.pdf")
    vault.save_narrative_report("doc_1", _sample_report(), "claude-3-5-sonnet")
    vault.delete_narrative_report("doc_1")
    assert vault.get_narrative_report("doc_1") is None


def test_delete_document_cascades_to_narrative_reports(vault):
    vault.insert_document("doc_1", "test.pdf")
    vault.save_narrative_report("doc_1", _sample_report(), "claude-3-5-sonnet")
    vault.delete_document("doc_1")
    assert vault.get_narrative_report("doc_1") is None
