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
