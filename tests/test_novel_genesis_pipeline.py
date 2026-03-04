"""
Tests for novel_genesis_pipeline.py

Exercises the Genesis Resolver layer (Schema Repairer, Continuity Arbitrator),
the VoiceDriftAccumulator, and the embedded run_internal_unit_tests harness.
"""

import pytest

from novel_genesis_pipeline import (
    LangGraphNovelGenesis,
    VoiceDriftAccumulator,
    run_internal_unit_tests,
)


@pytest.fixture
def pipeline() -> LangGraphNovelGenesis:
    """Shared pipeline instance. No API calls are made during construction."""
    return LangGraphNovelGenesis(api_key="test-key")


# ---------------------------------------------------------------------------
# TestSchemaRepairer
# ---------------------------------------------------------------------------


class TestSchemaRepairer:
    def test_extracts_json_from_markdown_code_block(self, pipeline):
        """Main spec case: malformed LLM response with markdown fence."""
        malformed = (
            "Analysis complete. ```json\n"
            '[{"mutation_type": "ADD_NODE", "target_id": "test_node"}]\n'
            "```"
        )
        result = pipeline.schema_repairer_node(
            {"active_node": "nse_mutation", "last_raw_response": malformed}
        )

        assert result["schema_repair_status"] == "OK"
        assert "nse_mutations" in result
        assert "test_node" in result["nse_mutations"]

    def test_passes_through_clean_json(self, pipeline):
        """Raw valid JSON array should parse and be keyed correctly."""
        raw = '[{"mutation_type": "ADD_NODE", "target_id": "node_a"}]'
        result = pipeline.schema_repairer_node(
            {"active_node": "nse_mutation", "last_raw_response": raw}
        )

        assert result["schema_repair_status"] == "OK"
        assert "nse_mutations" in result
        assert "node_a" in result["nse_mutations"]

    def test_nse_mutation_result_keyed_by_target_id(self, pipeline):
        """Each mutation dict must be accessible via its target_id as the key."""
        raw = (
            '[{"mutation_type": "ADD_EDGE", "target_id": "alpha"},'
            ' {"mutation_type": "MODIFY_NODE", "target_id": "beta"}]'
        )
        result = pipeline.schema_repairer_node(
            {"active_node": "nse_mutation", "last_raw_response": raw}
        )

        assert result["schema_repair_status"] == "OK"
        mutations = result["nse_mutations"]
        assert "alpha" in mutations
        assert "beta" in mutations
        assert mutations["alpha"]["mutation_type"] == "ADD_EDGE"
        assert mutations["beta"]["mutation_type"] == "MODIFY_NODE"

    def test_returns_failed_status_on_unparseable_input(self, pipeline):
        """Completely unparseable text must return FAILED status."""
        result = pipeline.schema_repairer_node(
            {
                "active_node": "nse_mutation",
                "last_raw_response": "This is just plain English. No JSON here!",
            }
        )

        assert result["schema_repair_status"] == "FAILED"
        assert "schema_repair_error" in result


# ---------------------------------------------------------------------------
# TestContinuityArbitrator
# ---------------------------------------------------------------------------


class TestContinuityArbitrator:
    def test_escalates_clean_verdict_when_violations_exist(self, pipeline):
        """Main spec case: CLEAN verdict with NSE violations -> REVISION RECOMMENDED."""
        result = pipeline.continuity_arbitrator_node(
            {
                "nse_violations": ["V1 KNOWLEDGE VIOLATION: char_01 acting on info_05"],
                "craft_symptoms": "Minor pacing issue.",
                "craft_verdict": "CLEAN",
            }
        )

        assert result.get("craft_verdict") == "REVISION RECOMMENDED"

    def test_no_change_when_no_violations(self, pipeline):
        """Empty violations list: CLEAN verdict is preserved, empty dict returned."""
        result = pipeline.continuity_arbitrator_node(
            {
                "nse_violations": [],
                "craft_symptoms": "Prose is clean.",
                "craft_verdict": "CLEAN",
            }
        )

        assert result == {}

    def test_no_change_when_already_revision_recommended(self, pipeline):
        """Violations present but verdict already elevated: no further change."""
        result = pipeline.continuity_arbitrator_node(
            {
                "nse_violations": ["V2 TIMELINE VIOLATION: event_03 precedes cause_01"],
                "craft_symptoms": "Existing symptom.",
                "craft_verdict": "REVISION RECOMMENDED",
            }
        )

        assert result == {}

    def test_nse_override_appended_to_craft_symptoms(self, pipeline):
        """The NSE override note must be appended to the updated craft_symptoms."""
        result = pipeline.continuity_arbitrator_node(
            {
                "nse_violations": [
                    "V1 KNOWLEDGE VIOLATION: char_01 acting on info_05",
                    "V2 TIMELINE VIOLATION: event_03 precedes cause_01",
                ],
                "craft_symptoms": "Slow opening.",
                "craft_verdict": "CLEAN",
            }
        )

        assert "craft_symptoms" in result
        assert "[NSE OVERRIDE]" in result["craft_symptoms"]
        assert "2 violation(s)" in result["craft_symptoms"]


# ---------------------------------------------------------------------------
# TestVoiceDriftAccumulator
# ---------------------------------------------------------------------------


class TestVoiceDriftAccumulator:
    def test_initial_drift_score_is_zero(self):
        """Freshly instantiated accumulator reports zero drift."""
        acc = VoiceDriftAccumulator()
        assert acc.current_score == 0.0

    def test_accumulates_drift_across_scenes(self):
        """current_score returns the last score; mean_drift returns the mean."""
        acc = VoiceDriftAccumulator()
        acc.record(0.1)
        acc.record(0.3)

        assert acc.current_score == 0.3
        assert abs(acc.mean_drift - 0.2) < 1e-9


# ---------------------------------------------------------------------------
# TestRunInternalUnitTests
# ---------------------------------------------------------------------------


class TestRunInternalUnitTests:
    def test_returns_true_on_passing_pipeline(self):
        """Embedded harness must return True when all Genesis Resolver tests pass."""
        assert run_internal_unit_tests(api_key="test-key-does-not-matter") is True
