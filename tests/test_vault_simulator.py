import pytest
from core.vault import HybridVault


@pytest.fixture
def vault(tmp_path):
    v = HybridVault(tenant_id="test_simulator", base_dir=str(tmp_path))
    yield v
    v.conn.close()


def _sample_result():
    return {
        "p50_delay_days": 12,
        "p90_delay_days": 34,
        "iterations": 10000,
        "critical_path": ["node_a", "node_b"],
    }


def test_save_and_get_risk_simulation(vault):
    vault.insert_document("doc_1", "test.pdf")
    result = _sample_result()
    vault.save_risk_simulation("doc_1", result)
    retrieved = vault.get_risk_simulation("doc_1")
    assert retrieved is not None
    assert retrieved == result


def test_get_returns_none_when_absent(vault):
    assert vault.get_risk_simulation("doc_missing") is None


def test_save_upserts_on_conflict(vault):
    vault.insert_document("doc_1", "test.pdf")
    vault.save_risk_simulation("doc_1", _sample_result())
    updated = {"p50_delay_days": 5, "p90_delay_days": 10, "iterations": 5000, "critical_path": []}
    vault.save_risk_simulation("doc_1", updated)
    result = vault.get_risk_simulation("doc_1")
    assert result["p50_delay_days"] == 5
    assert result["iterations"] == 5000


def test_delete_removes_row(vault):
    vault.insert_document("doc_1", "test.pdf")
    vault.save_risk_simulation("doc_1", _sample_result())
    vault.delete_risk_simulation("doc_1")
    assert vault.get_risk_simulation("doc_1") is None


def test_delete_document_cascades_to_risk_simulations(vault):
    vault.insert_document("doc_1", "test.pdf")
    vault.save_risk_simulation("doc_1", _sample_result())
    vault.delete_document("doc_1")
    assert vault.get_risk_simulation("doc_1") is None


def test_has_temporal_data_returns_true_when_rows_exist(vault):
    vault.insert_document("doc_1", "test.pdf")
    cursor = vault.conn.cursor()
    # Insert nodes
    cursor.execute("INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)", ("node_a", "TASK", "Task A"))
    cursor.execute("INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)", ("node_b", "TASK", "Task B"))
    vault.conn.commit()
    # Insert an edge linking node_a -> node_b for doc_1
    cursor.execute(
        "INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id) VALUES (?, ?, ?, ?, ?, ?)",
        ("doc_1_edge_1", "doc_1", "node_a", "node_b", "STARTS_AFTER", "chunk_1")
    )
    vault.conn.commit()
    # Insert temporal metadata for node_a
    cursor.execute(
        "INSERT OR REPLACE INTO temporal_metadata (node_id, start_date, end_date) VALUES (?, ?, ?)",
        ("node_a", "2026-01-01", "2026-03-01")
    )
    vault.conn.commit()

    assert vault.has_temporal_data("doc_1") is True


def test_has_temporal_data_returns_false_when_no_rows(vault):
    vault.insert_document("doc_2", "empty.pdf")
    assert vault.has_temporal_data("doc_2") is False
