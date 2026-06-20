import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, call

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


def _valid_body(**overrides):
    body = {
        "LLM_PROVIDER": "openrouter",
        "OPENAI_API_KEY": "",
        "OPENROUTER_API_KEY": "sk-or-v1-newvalue",
        "FAST_MODEL": "gpt-4o-mini",
        "SMART_MODEL": "gpt-4o",
        "VAULT_PATH": "./vaults",
        "DIAMOND_MINER_PIPELINE_MODE": "claims",
    }
    body.update(overrides)
    return body


class TestPostConfig:
    def test_returns_applied_status(self, client):
        test_client, _ = client
        with patch("api.load_dotenv"):
            response = test_client.post("/api/v1/config", json=_valid_body())
        assert response.status_code == 200
        assert response.json() == {"status": "applied"}

    def test_writes_env_file(self, client):
        test_client, env_file = client
        with patch("api.load_dotenv"):
            test_client.post("/api/v1/config", json=_valid_body())
        content = env_file.read_text()
        assert 'LLM_PROVIDER="openrouter"' in content
        assert 'FAST_MODEL="gpt-4o-mini"' in content
        assert 'DIAMOND_MINER_PIPELINE_MODE="claims"' in content
        assert "DIAMOND_MINER_CLAIM_LAYER" not in content
        assert "DIAMOND_MINER_USE_CLAIM_PROMOTION" not in content

    def test_calls_load_dotenv_with_override(self, client):
        test_client, env_file = client
        with patch("api.load_dotenv") as mock_ld:
            test_client.post("/api/v1/config", json=_valid_body())
        mock_ld.assert_called_once_with(dotenv_path=env_file, override=True)

    def test_rejects_invalid_provider_with_422(self, client):
        test_client, _ = client
        with patch("api.load_dotenv"):
            response = test_client.post(
                "/api/v1/config",
                json=_valid_body(LLM_PROVIDER="anthropic"),
            )
        assert response.status_code == 422

    def test_rejects_invalid_pipeline_mode_with_422(self, client):
        test_client, _ = client
        with patch("api.load_dotenv"):
            response = test_client.post(
                "/api/v1/config",
                json=_valid_body(DIAMOND_MINER_PIPELINE_MODE="invalid"),
            )
        assert response.status_code == 422

    def test_masked_key_preserves_existing_value(self, client):
        test_client, env_file = client
        env_file.write_text('OPENROUTER_API_KEY="sk-or-v1-original-secret"\n')
        with patch("api.load_dotenv"):
            test_client.post(
                "/api/v1/config",
                json=_valid_body(OPENROUTER_API_KEY="sk-or-v1-ori\u2026"),
            )
        content = env_file.read_text()
        assert 'OPENROUTER_API_KEY="sk-or-v1-original-secret"' in content

    def test_empty_key_value_not_written(self, client):
        test_client, env_file = client
        with patch("api.load_dotenv"):
            test_client.post("/api/v1/config", json=_valid_body(OPENAI_API_KEY=""))
        content = env_file.read_text()
        assert "OPENAI_API_KEY" not in content

    def test_round_trip_get_after_post(self, client):
        test_client, env_file = client
        with patch("api.load_dotenv"):
            test_client.post("/api/v1/config", json=_valid_body(FAST_MODEL="gpt-4o", DIAMOND_MINER_PIPELINE_MODE="shadow"))
        response = test_client.get("/api/v1/config")
        assert response.json()["FAST_MODEL"] == "gpt-4o"
        assert response.json()["DIAMOND_MINER_PIPELINE_MODE"] == "shadow"

    def test_accepts_legacy_flags_for_compatibility(self, client):
        test_client, env_file = client
        body = _valid_body(DIAMOND_MINER_PIPELINE_MODE="")
        body.update({
            "DIAMOND_MINER_CLAIM_LAYER": "1",
            "DIAMOND_MINER_USE_CLAIM_PROMOTION": "1",
        })

        with patch("api.load_dotenv"):
            response = test_client.post("/api/v1/config", json=body)

        assert response.status_code == 200
        content = env_file.read_text()
        assert 'DIAMOND_MINER_CLAIM_LAYER="1"' in content
        assert 'DIAMOND_MINER_USE_CLAIM_PROMOTION="1"' in content
