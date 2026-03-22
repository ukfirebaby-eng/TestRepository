import pytest
from core.vault import HybridVault


@pytest.fixture
def vault(tmp_path):
    v = HybridVault(tenant_id="test_temporal", base_dir=str(tmp_path))
    yield v
    v.conn.close()


def _seed_nodes_and_edges(vault, document_id="doc_t1"):
    """Seeds the minimum required graph data for temporal queries."""
    vault.insert_document(document_id, "test.pdf")
    cursor = vault.conn.cursor()
    cursor.executemany(
        "INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
        [("node_a", "Task", "Phase A"), ("node_b", "Task", "Phase B")]
    )
    # STARTS_AFTER edge: B starts after A
    cursor.execute("""
        INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ("e1", document_id, "node_a", "node_b", "STARTS_AFTER", "chunk_1"))
    vault.conn.commit()


class TestTemporalSchema:
    def test_temporal_metadata_table_exists(self, vault):
        cursor = vault.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='temporal_metadata'"
        )
        assert cursor.fetchone() is not None

    def test_temporal_metadata_columns(self, vault):
        cursor = vault.conn.cursor()
        cursor.execute("PRAGMA table_info(temporal_metadata)")
        cols = {row[1] for row in cursor.fetchall()}
        assert {"node_id", "start_date", "end_date", "duration_days", "is_milestone"} <= cols


class TestInsertTemporalData:
    def test_inserts_temporal_node(self, vault):
        _seed_nodes_and_edges(vault)
        vault.insert_temporal_data([{
            "node_id": "node_a",
            "start_date": "2026-04-01",
            "end_date": "2026-04-30",
            "duration_days": 30,
            "is_milestone": False
        }])
        cursor = vault.conn.cursor()
        cursor.execute("SELECT start_date FROM temporal_metadata WHERE node_id = 'node_a'")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "2026-04-01"

    def test_upsert_overwrites_existing(self, vault):
        _seed_nodes_and_edges(vault)
        vault.insert_temporal_data([{
            "node_id": "node_a", "start_date": "2026-04-01",
            "end_date": "2026-04-30", "duration_days": 30, "is_milestone": False
        }])
        # Refine with a more specific date
        vault.insert_temporal_data([{
            "node_id": "node_a", "start_date": "2026-04-15",
            "end_date": "2026-04-30", "duration_days": 15, "is_milestone": True
        }])
        cursor = vault.conn.cursor()
        cursor.execute("SELECT start_date, is_milestone FROM temporal_metadata WHERE node_id = 'node_a'")
        row = cursor.fetchone()
        assert row[0] == "2026-04-15"
        assert row[1] == 1  # True stored as 1

    def test_handles_empty_list(self, vault):
        vault.insert_temporal_data([])  # Must not raise


class TestGetChronologicalFriction:
    def test_detects_negative_slack(self, vault):
        _seed_nodes_and_edges(vault)
        # A ends 2026-05-31; B starts 2026-04-01 < A's end → Negative Slack
        vault.insert_temporal_data([
            {"node_id": "node_a", "start_date": "2026-04-01", "end_date": "2026-05-31",
             "duration_days": 60, "is_milestone": False},
            {"node_id": "node_b", "start_date": "2026-04-01", "end_date": "2026-04-30",
             "duration_days": 30, "is_milestone": False},
        ])
        conflicts = vault.get_chronological_friction(document_id="doc_t1")
        assert len(conflicts) == 1
        assert conflicts[0]["predecessor"] == "node_a"
        assert conflicts[0]["successor"] == "node_b"

    def test_no_friction_when_successor_starts_after_predecessor_ends(self, vault):
        _seed_nodes_and_edges(vault)
        # A ends 2026-03-31; B starts 2026-04-01 > A's end → valid schedule
        vault.insert_temporal_data([
            {"node_id": "node_a", "start_date": "2026-03-01", "end_date": "2026-03-31",
             "duration_days": 31, "is_milestone": False},
            {"node_id": "node_b", "start_date": "2026-04-01", "end_date": "2026-04-30",
             "duration_days": 30, "is_milestone": False},
        ])
        conflicts = vault.get_chronological_friction(document_id="doc_t1")
        assert conflicts == []

    def test_returns_empty_with_no_temporal_data(self, vault):
        _seed_nodes_and_edges(vault)
        conflicts = vault.get_chronological_friction(document_id="doc_t1")
        assert conflicts == []
