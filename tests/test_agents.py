import json
import pytest
from unittest.mock import patch, MagicMock
from core.agents import ContradictionHunterAgent


def _mock_response(payload: dict):
    mock = MagicMock()
    mock.choices[0].message.content = json.dumps(payload)
    return mock


class TestContradictionHunterAgentSchema:
    def test_prompt_requests_structured_risk_finding(self):
        assert '"finding"' in ContradictionHunterAgent.SYSTEM_PROMPT
        assert "affected_entity" in ContradictionHunterAgent.SYSTEM_PROMPT
        assert "blocking_condition" in ContradictionHunterAgent.SYSTEM_PROMPT
        assert "recommended_action" in ContradictionHunterAgent.SYSTEM_PROMPT

    def test_returns_severity_and_probability_on_genuine(self):
        payload = {"is_genuine": True, "confidence": 0.9, "analysis": "Fix it.", "severity": 4, "probability": 3}
        with patch("core.agents._get_client") as mock_client:
            mock_client().chat.completions.create.return_value = _mock_response(payload)
            result = ContradictionHunterAgent.synthesize_mitigation("A REQUIRES B but C BLOCKS B", "text")
        assert "severity" in result
        assert "probability" in result

    def test_severity_and_probability_are_integers(self):
        payload = {"is_genuine": True, "confidence": 0.8, "analysis": "X.", "severity": 3, "probability": 2}
        with patch("core.agents._get_client") as mock_client:
            mock_client().chat.completions.create.return_value = _mock_response(payload)
            result = ContradictionHunterAgent.synthesize_mitigation("clash", "text")
        assert isinstance(result["severity"], int)
        assert isinstance(result["probability"], int)

    def test_error_fallback_includes_severity_probability(self):
        with patch("core.agents._get_client") as mock_client:
            mock_client().chat.completions.create.side_effect = Exception("API down")
            result = ContradictionHunterAgent.synthesize_mitigation("clash", "text")
        assert result["severity"] == 1
        assert result["probability"] == 1
        assert result["is_genuine"] is False

    def test_spurious_conflict_returns_severity_probability(self):
        payload = {"is_genuine": False, "confidence": 0.2, "analysis": "Not real.", "severity": 1, "probability": 1}
        with patch("core.agents._get_client") as mock_client:
            mock_client().chat.completions.create.return_value = _mock_response(payload)
            result = ContradictionHunterAgent.synthesize_mitigation("clash", "text")
        assert result["severity"] == 1
        assert result["probability"] == 1
