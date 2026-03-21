import pytest
from core.vault import HybridVault


@pytest.fixture
def vault(tmp_path):
    v = HybridVault(tenant_id="test_fragility", base_dir=str(tmp_path))
    yield v
    v.conn.close()


class TestSchema:
    def test_fragility_lines_table_exists(self, vault):
        cursor = vault.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fragility_lines'"
        )
        assert cursor.fetchone() is not None

    def test_fragility_lines_index_exists(self, vault):
        cursor = vault.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_fragility_lines_document'"
        )
        assert cursor.fetchone() is not None


def _seed_requires_graph(vault, document_id="doc_hub"):
    """Seeds a graph where node_b has 3 incoming REQUIRES edges — a hub."""
    vault.insert_document(document_id, "hub_test.pdf")
    cursor = vault.conn.cursor()
    for name in ["node_a", "node_b", "node_c", "node_d", "node_e"]:
        cursor.execute(
            "INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
            (name, "Concept", name.replace("_", " ").title())
        )
    # node_b is the hub: a, c, d all REQUIRE it
    for src in ["node_a", "node_c", "node_d"]:
        cursor.execute(
            "INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (f"{document_id}_{src}_req_b", document_id, src, "node_b", "REQUIRES", f"{document_id}_chunk_1")
        )
    # node_e has only 1 REQUIRES edge — below threshold
    cursor.execute(
        "INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"{document_id}_a_req_e", document_id, "node_a", "node_e", "REQUIRES", f"{document_id}_chunk_1")
    )
    vault.conn.commit()


class TestReadMethods:
    def test_get_hub_nodes_returns_hub_above_threshold(self, vault):
        _seed_requires_graph(vault)
        hubs = vault.get_hub_nodes("doc_hub", min_dependents=3)
        assert len(hubs) == 1
        assert hubs[0]["id"] == "node_b"
        assert hubs[0]["dependency_count"] == 3

    def test_get_hub_nodes_includes_dependent_node_ids(self, vault):
        _seed_requires_graph(vault)
        hubs = vault.get_hub_nodes("doc_hub", min_dependents=3)
        dep_ids = set(hubs[0]["dependent_node_ids"])
        assert dep_ids == {"node_a", "node_c", "node_d"}

    def test_get_hub_nodes_respects_min_dependents(self, vault):
        _seed_requires_graph(vault)
        hubs = vault.get_hub_nodes("doc_hub", min_dependents=4)
        assert hubs == []

    def test_get_hub_nodes_scoped_to_document(self, vault):
        """Scoping test uses distinct node IDs so the assertion is falsifiable."""
        _seed_requires_graph(vault, "doc_hub")
        # Seed doc_other with different nodes that should NOT appear in doc_hub results
        vault.insert_document("doc_other", "other.pdf")
        cursor = vault.conn.cursor()
        for name in ["other_a", "other_b", "other_c", "other_d"]:
            cursor.execute(
                "INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
                (name, "Concept", name)
            )
        for src in ["other_a", "other_c", "other_d"]:
            cursor.execute(
                "INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (f"doc_other_{src}_req_b", "doc_other", src, "other_b", "REQUIRES", "doc_other_chunk_1")
            )
        vault.conn.commit()
        hubs = vault.get_hub_nodes("doc_hub", min_dependents=3)
        assert len(hubs) == 1
        assert hubs[0]["id"] == "node_b"  # not other_b

    def test_get_node_source_chunk_returns_chunk_id(self, vault):
        _seed_requires_graph(vault)
        chunk_id = vault.get_node_source_chunk("node_b", "doc_hub")
        assert chunk_id == "doc_hub_chunk_1"

    def test_get_node_source_chunk_returns_none_when_no_edge(self, vault):
        _seed_requires_graph(vault)
        chunk_id = vault.get_node_source_chunk("node_b", "doc_nonexistent")
        assert chunk_id is None

    def test_get_fragility_lines_returns_empty_when_none(self, vault):
        vault.insert_document("doc_empty_fl", "x.pdf")
        assert vault.get_fragility_lines("doc_empty_fl") == []

    def test_get_fragility_lines_returns_persisted_results(self, vault):
        vault.insert_document("doc_fl", "x.pdf")
        cursor = vault.conn.cursor()
        cursor.execute(
            "INSERT INTO fragility_lines (id, document_id, hub_node_id, insight, cascade_nodes) "
            "VALUES (?, ?, ?, ?, ?)",
            ("fl_1", "doc_fl", "node_b", "Critical bottleneck.", '["Node A", "Node C"]')
        )
        vault.conn.commit()
        results = vault.get_fragility_lines("doc_fl")
        assert len(results) == 1
        assert results[0]["hub_node_id"] == "node_b"
        assert results[0]["insight"] == "Critical bottleneck."
        assert results[0]["cascade_nodes"] == ["Node A", "Node C"]


class TestWriteMethods:
    def test_upsert_fragility_lines_persists_results(self, vault):
        vault.insert_document("doc_w", "x.pdf")
        results = [
            {"hub_node_id": "node_b", "insight": "Critical bottleneck.", "cascade_nodes": ["Node A", "Node C"]},
        ]
        vault.upsert_fragility_lines("doc_w", results)
        lines = vault.get_fragility_lines("doc_w")
        assert len(lines) == 1
        assert lines[0]["hub_node_id"] == "node_b"
        assert lines[0]["cascade_nodes"] == ["Node A", "Node C"]

    def test_upsert_fragility_lines_replaces_old_results(self, vault):
        vault.insert_document("doc_w2", "x.pdf")
        vault.upsert_fragility_lines("doc_w2", [
            {"hub_node_id": "node_old", "insight": "Old.", "cascade_nodes": []}
        ])
        vault.upsert_fragility_lines("doc_w2", [
            {"hub_node_id": "node_new", "insight": "New.", "cascade_nodes": ["X"]}
        ])
        lines = vault.get_fragility_lines("doc_w2")
        assert len(lines) == 1
        assert lines[0]["hub_node_id"] == "node_new"

    def test_upsert_fragility_lines_empty_clears_results(self, vault):
        vault.insert_document("doc_w3", "x.pdf")
        vault.upsert_fragility_lines("doc_w3", [
            {"hub_node_id": "node_b", "insight": "X.", "cascade_nodes": []}
        ])
        vault.upsert_fragility_lines("doc_w3", [])
        assert vault.get_fragility_lines("doc_w3") == []
