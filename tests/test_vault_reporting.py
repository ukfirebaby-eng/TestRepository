import pytest
from core.vault import HybridVault


@pytest.fixture
def vault(tmp_path):
    v = HybridVault(tenant_id="test_reporting", base_dir=str(tmp_path))
    yield v
    v.conn.close()


def _seed_hub_graph(vault, document_id="doc_hubs"):
    """Seeds a graph where node_b has 2 REQUIRES + 1 STARTS_AFTER = 3 inbound,
    and node_c has 1 REQUIRES = 1 inbound (below any reasonable threshold)."""
    vault.insert_document(document_id, "hub_report_test.pdf")
    cursor = vault.conn.cursor()
    for name in ["node_a", "node_b", "node_c", "node_d", "node_e"]:
        cursor.execute(
            "INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
            (name, "Concept", name.replace("_", " ").title())
        )
    # node_b: 2x REQUIRES + 1x STARTS_AFTER = 3 inbound
    for src, rel in [("node_a", "REQUIRES"), ("node_d", "REQUIRES"), ("node_e", "STARTS_AFTER")]:
        cursor.execute(
            "INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (f"{document_id}_{src}_{rel}_b", document_id, src, "node_b", rel, f"{document_id}_chunk_1")
        )
    # node_c: 1x REQUIRES only
    cursor.execute(
        "INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"{document_id}_a_req_c", document_id, "node_a", "node_c", "REQUIRES", f"{document_id}_chunk_1")
    )
    vault.conn.commit()


class TestGetHubVulnerabilities:
    def test_returns_list(self, vault):
        _seed_hub_graph(vault)
        result = vault.get_hub_vulnerabilities("doc_hubs")
        assert isinstance(result, list)

    def test_hub_node_returned_with_correct_count(self, vault):
        _seed_hub_graph(vault)
        result = vault.get_hub_vulnerabilities("doc_hubs")
        assert len(result) == 2
        top = result[0]
        assert top["id"] == "node_b"
        assert top["dependency_count"] == 3

    def test_result_includes_name_and_label(self, vault):
        _seed_hub_graph(vault)
        result = vault.get_hub_vulnerabilities("doc_hubs")
        top = result[0]
        assert top["name"] == "Node B"
        assert top["label"] == "Concept"

    def test_ordered_by_dependency_count_descending(self, vault):
        _seed_hub_graph(vault)
        result = vault.get_hub_vulnerabilities("doc_hubs")
        counts = [r["dependency_count"] for r in result]
        assert counts == sorted(counts, reverse=True)

    def test_limit_respected(self, vault):
        _seed_hub_graph(vault)
        result = vault.get_hub_vulnerabilities("doc_hubs", limit=1)
        assert len(result) == 1

    def test_scoped_to_document(self, vault):
        _seed_hub_graph(vault, "doc_a")
        # Seed a second document with its own hub — should NOT appear in doc_a results
        vault.insert_document("doc_b", "other.pdf")
        cursor = vault.conn.cursor()
        for name in ["b_x", "b_y", "b_z", "b_hub"]:
            cursor.execute(
                "INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
                (name, "Concept", name)
            )
        for src in ["b_x", "b_y", "b_z"]:
            cursor.execute(
                "INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (f"doc_b_{src}_req_hub", "doc_b", src, "b_hub", "REQUIRES", "doc_b_chunk_1")
            )
        vault.conn.commit()
        result = vault.get_hub_vulnerabilities("doc_a")
        ids = [r["id"] for r in result]
        assert "b_hub" not in ids

    def test_empty_document_returns_empty_list(self, vault):
        vault.insert_document("doc_empty", "empty.pdf")
        result = vault.get_hub_vulnerabilities("doc_empty")
        assert result == []
