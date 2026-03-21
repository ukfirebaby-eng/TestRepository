import pytest
from core.vault import HybridVault


@pytest.fixture
def vault(tmp_path):
    """Creates a fresh HybridVault in a temporary directory."""
    v = HybridVault(tenant_id="test_delete", base_dir=str(tmp_path))
    yield v
    v.conn.close()


def _seed_document(vault, document_id="doc_test"):
    """Inserts a minimal document with one edge and one friction line."""
    vault.insert_document(document_id, "test.pdf")

    vault.collection.add(
        ids=[f"{document_id}_chunk_1"],
        documents=["some text"],
        metadatas=[{"document_id": document_id, "page_number": 1,
                    "x0": 0.0, "y0": 0.0, "x1": 1.0, "y1": 1.0}]
    )

    cursor = vault.conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
                   ("node_a", "Concept", "Alpha"))
    cursor.execute("INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
                   ("node_b", "Concept", "Beta"))
    cursor.execute(
        "INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"{document_id}_edge_1", document_id, "node_a", "node_b", "REQUIRES", f"{document_id}_chunk_1")
    )
    vault.conn.commit()

    vault.upsert_friction_lines(document_id, [{
        "source": "node_a",
        "target": "node_b",
        "diamond": "A conflicts with B.",
        "provenance_ids": [f"{document_id}_chunk_1"]
    }])


def _seed_fragility_line(vault, document_id="doc_test"):
    """Adds a fragility line for the given document."""
    vault.upsert_fragility_lines(document_id, [
        {"hub_node_id": "node_a", "insight": "Critical.", "cascade_nodes": ["Node B"]}
    ])


class TestDeleteDocument:
    def test_deletes_document_record(self, vault):
        _seed_document(vault)
        vault.delete_document("doc_test")
        cursor = vault.conn.cursor()
        cursor.execute("SELECT id FROM documents WHERE id = 'doc_test'")
        assert cursor.fetchone() is None

    def test_deletes_edges(self, vault):
        _seed_document(vault)
        vault.delete_document("doc_test")
        cursor = vault.conn.cursor()
        cursor.execute("SELECT id FROM edges WHERE document_id = 'doc_test'")
        assert cursor.fetchall() == []

    def test_deletes_friction_lines(self, vault):
        _seed_document(vault)
        vault.delete_document("doc_test")
        cursor = vault.conn.cursor()
        cursor.execute("SELECT id FROM friction_lines WHERE document_id = 'doc_test'")
        assert cursor.fetchall() == []

    def test_deletes_chroma_embeddings(self, vault):
        _seed_document(vault)
        vault.delete_document("doc_test")
        result = vault.collection.get(where={"document_id": {"$eq": "doc_test"}})
        assert result["ids"] == []

    def test_does_not_delete_nodes(self, vault):
        """Nodes are shared and must not be deleted."""
        _seed_document(vault)
        vault.delete_document("doc_test")
        cursor = vault.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM nodes")
        assert cursor.fetchone()[0] == 2

    def test_no_op_when_document_has_no_chunks(self, vault):
        """delete_document() must not raise when the document has zero ChromaDB chunks."""
        vault.insert_document("doc_empty", "empty.pdf")
        # No chunks added — ChromaDB delete would raise if called blindly
        vault.delete_document("doc_empty")
        cursor = vault.conn.cursor()
        cursor.execute("SELECT id FROM documents WHERE id = 'doc_empty'")
        assert cursor.fetchone() is None

    def test_does_not_affect_other_documents(self, vault):
        """Deleting one document must not touch another document's data."""
        _seed_document(vault, "doc_a")
        _seed_document(vault, "doc_b")
        vault.delete_document("doc_a")
        cursor = vault.conn.cursor()
        cursor.execute("SELECT id FROM documents WHERE id = 'doc_b'")
        assert cursor.fetchone() is not None
        cursor.execute("SELECT COUNT(*) FROM edges WHERE document_id = 'doc_b'")
        assert cursor.fetchone()[0] == 1

    def test_deletes_fragility_lines(self, vault):
        _seed_document(vault)
        _seed_fragility_line(vault)
        vault.delete_document("doc_test")
        cursor = vault.conn.cursor()
        cursor.execute("SELECT id FROM fragility_lines WHERE document_id = 'doc_test'")
        assert cursor.fetchall() == []
