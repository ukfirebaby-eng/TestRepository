import json
import pytest
from unittest.mock import MagicMock, patch
from core.agents import ChronosAgent


def make_mock_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


VALID_TEMPORAL_JSON = json.dumps({
    "temporal_nodes": [
        {
            "node_id": "node_a",
            "start_date": "2026-04-01",
            "end_date": "2026-04-30",
            "duration_days": 30,
            "is_milestone": False
        }
    ],
    "temporal_edges": [
        {"source_id": "node_a", "target_id": "node_b", "relationship": "STARTS_AFTER"}
    ]
})


def test_get_system_prompt_contains_anchor():
    prompt = ChronosAgent.get_system_prompt("2026-03-22")
    assert "2026-03-22" in prompt
    assert "ISO 8601" in prompt


def test_get_system_prompt_varies_with_date():
    p1 = ChronosAgent.get_system_prompt("2026-01-01")
    p2 = ChronosAgent.get_system_prompt("2026-06-15")
    assert "2026-01-01" in p1
    assert "2026-06-15" in p2
    assert p1 != p2


def test_extract_time_data_returns_dict():
    with patch("core.agents._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.chat.completions.create.return_value = make_mock_response(VALID_TEMPORAL_JSON)
        result = ChronosAgent.extract_time_data("The project starts next month.", ["node_a"])
    assert isinstance(result, dict)
    assert "temporal_nodes" in result
    assert "temporal_edges" in result


def test_extract_time_data_passes_node_ids_to_prompt():
    with patch("core.agents._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.chat.completions.create.return_value = make_mock_response(VALID_TEMPORAL_JSON)
        ChronosAgent.extract_time_data("Some text.", ["node_x", "node_y"])
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        user_content = call_kwargs["messages"][1]["content"]
    assert "node_x" in user_content
    assert "node_y" in user_content


def test_extract_time_data_returns_empty_on_failure():
    with patch("core.agents._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API down")
        result = ChronosAgent.extract_time_data("Some text.", ["node_a"])
    assert result == {"temporal_nodes": [], "temporal_edges": []}
