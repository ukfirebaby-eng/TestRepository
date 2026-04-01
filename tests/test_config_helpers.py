import pytest
from pathlib import Path
from core.config import read_env, write_env, mask_key, _ENV_KEYS


class TestReadEnv:
    def test_returns_empty_dict_when_file_missing(self, tmp_path):
        result = read_env(tmp_path / "nonexistent.env")
        assert result == {}

    def test_parses_known_keys(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text('LLM_PROVIDER="openrouter"\nFAST_MODEL="gpt-4o-mini"\n')
        result = read_env(env)
        assert result["LLM_PROVIDER"] == "openrouter"
        assert result["FAST_MODEL"] == "gpt-4o-mini"

    def test_strips_quotes(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("OPENAI_API_KEY='sk-proj-abc'\n")
        result = read_env(env)
        assert result["OPENAI_API_KEY"] == "sk-proj-abc"

    def test_ignores_comments_and_blank_lines(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("# comment\n\nLLM_PROVIDER=\"openai\"\n")
        result = read_env(env)
        assert "LLM_PROVIDER" in result
        assert len(result) == 1


class TestWriteEnv:
    def test_writes_managed_keys(self, tmp_path):
        env = tmp_path / ".env"
        write_env(env, {"LLM_PROVIDER": "openai", "FAST_MODEL": "gpt-4o-mini"})
        content = env.read_text()
        assert 'LLM_PROVIDER="openai"' in content
        assert 'FAST_MODEL="gpt-4o-mini"' in content

    def test_preserves_comments(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("# my comment\nLLM_PROVIDER=\"openrouter\"\n")
        write_env(env, {"LLM_PROVIDER": "openai"})
        content = env.read_text()
        assert "# my comment" in content

    def test_preserves_unmanaged_keys(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text('CUSTOM_VAR="keep-me"\nLLM_PROVIDER="openai"\n')
        write_env(env, {"LLM_PROVIDER": "openrouter"})
        content = env.read_text()
        assert 'CUSTOM_VAR="keep-me"' in content

    def test_omits_empty_values(self, tmp_path):
        env = tmp_path / ".env"
        write_env(env, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": ""})
        content = env.read_text()
        assert "OPENAI_API_KEY" not in content

    def test_round_trip(self, tmp_path):
        env = tmp_path / ".env"
        original = {
            "LLM_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "sk-or-v1-abc123",
            "FAST_MODEL": "gpt-4o-mini",
            "SMART_MODEL": "gpt-4o",
        }
        write_env(env, original)
        result = read_env(env)
        for key, val in original.items():
            assert result[key] == val


class TestMaskKey:
    def test_masks_long_values(self):
        assert mask_key("sk-or-v1-285fb99cc144") == "sk-or-v1-285\u2026"

    def test_does_not_mask_short_values(self):
        assert mask_key("short") == "short"

    def test_does_not_mask_empty_string(self):
        assert mask_key("") == ""

    def test_masks_exactly_at_12_chars(self):
        # 12 chars exactly — not masked (only >12 triggers masking)
        assert mask_key("abcdefghijkl") == "abcdefghijkl"

    def test_masks_13_chars(self):
        assert mask_key("abcdefghijklm") == "abcdefghijkl…"
