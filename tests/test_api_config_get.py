import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api import app


def _make_mock_vault():
    mock = MagicMock()
    mock.list_documents.return_value = []
    return mock


@pytest.fixture
def client(tmp_path):
    env_file = tmp_path / ".env"
    mock_vault = _make_mock_vault()
    with patch("api.vault", mock_vault), patch("api._env_path", return_value=env_file):
        with TestClient(app) as c:
            yield c, env_file


class TestGetConfig:
    def test_returns_empty_strings_when_no_env_file(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/config")
        assert response.status_code == 200
        body = response.json()
        assert body["LLM_PROVIDER"] == ""
        assert body["FAST_MODEL"] == ""

    def test_returns_all_expected_keys(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/config")
        assert response.status_code == 200
        body = response.json()
        for key in ("LLM_PROVIDER", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
                    "FAST_MODEL", "SMART_MODEL", "VAULT_PATH",
                    "DIAMOND_MINER_CLAIM_LAYER"):
            assert key in body

    def test_returns_plain_values_for_non_key_fields(self, client):
        test_client, env_file = client
        env_file.write_text(
            'LLM_PROVIDER="openrouter"\n'
            'FAST_MODEL="gpt-4o-mini"\n'
            'DIAMOND_MINER_CLAIM_LAYER="1"\n'
        )
        response = test_client.get("/api/v1/config")
        body = response.json()
        assert body["LLM_PROVIDER"] == "openrouter"
        assert body["FAST_MODEL"] == "gpt-4o-mini"
        assert body["DIAMOND_MINER_CLAIM_LAYER"] == "1"

    def test_masks_api_keys_longer_than_12_chars(self, client):
        test_client, env_file = client
        env_file.write_text('OPENROUTER_API_KEY="sk-or-v1-285fb99cc144"\n')
        response = test_client.get("/api/v1/config")
        body = response.json()
        assert body["OPENROUTER_API_KEY"] == "sk-or-v1-285\u2026"

    def test_does_not_mask_short_or_empty_keys(self, client):
        test_client, env_file = client
        env_file.write_text('OPENAI_API_KEY="short"\n')
        response = test_client.get("/api/v1/config")
        body = response.json()
        assert body["OPENAI_API_KEY"] == "short"
