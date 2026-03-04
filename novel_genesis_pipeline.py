"""
Novel Genesis Pipeline
======================
LangGraph-based novel generation pipeline with NSE mutation tracking,
continuity arbitration, and prose quality assessment.

Usage (CLI)::

    python novel_genesis_pipeline.py --api-key <KEY> --run-tests
    python novel_genesis_pipeline.py --api-key <KEY> --scenes 30

Requires (optional runtime):
    langgraph>=0.2
    langchain-openai>=0.1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from typing import Any

# Optional LangGraph import — individual node methods work without it.
try:
    from langgraph.graph import END, StateGraph

    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False


# ---------------------------------------------------------------------------
# VoiceDriftAccumulator
# ---------------------------------------------------------------------------


@dataclass
class VoiceDriftAccumulator:
    """Tracks per-scene voice drift scores for a novel generation run.

    Voice drift measures stylistic deviation from an established authorial
    baseline. Scores are recorded per scene and exposed as aggregate properties.
    """

    def __post_init__(self) -> None:
        self._history: list[float] = []

    def record(self, score: float) -> None:
        """Append a drift score for the most recently generated scene."""
        self._history.append(score)

    @property
    def current_score(self) -> float:
        """Return the most recently recorded drift score (0.0 if no scores yet)."""
        return self._history[-1] if self._history else 0.0

    @property
    def mean_drift(self) -> float:
        """Return the mean drift score across all recorded scenes (0.0 if empty)."""
        return sum(self._history) / len(self._history) if self._history else 0.0

    def reset(self) -> None:
        """Clear all accumulated drift data."""
        self._history.clear()


# ---------------------------------------------------------------------------
# LangGraphNovelGenesis
# ---------------------------------------------------------------------------


class LangGraphNovelGenesis:
    """LangGraph-based novel generation pipeline.

    Encapsulates the Genesis Resolver layer:
      - Schema Repairer: robust JSON extraction from malformed LLM responses.
      - Continuity Arbitrator: NSE-enforced narrative consistency checks.
      - Surgical Stylist: stub for high-fidelity prose revision.

    Node methods are independently testable without LangGraph or a live LLM.

    Class Attributes
    ----------------
    NODE_STATE_KEY_MAP : dict[str, str]
        Maps active_node names to the state key the schema repairer populates.
    """

    NODE_STATE_KEY_MAP: dict[str, str] = {
        "nse_mutation": "nse_mutations",
    }

    def __init__(self, api_key: str | None = None, max_scenes: int = 30) -> None:
        """Initialise the pipeline.

        Args:
            api_key:    OpenAI-compatible API key. Stored but not used at
                        construction time; no network calls are made here.
            max_scenes: Number of scenes to generate in a full pipeline run.
        """
        self._api_key = api_key
        self.max_scenes = max_scenes
        self._drift_accumulator = VoiceDriftAccumulator()
        self._graph = None
        if _LANGGRAPH_AVAILABLE:
            self._graph = self._build_graph()

    # ------------------------------------------------------------------
    # Graph construction (LangGraph only)
    # ------------------------------------------------------------------

    def _build_graph(self):
        """Construct and compile the LangGraph state machine.

        Node wiring:
            schema_repairer -> continuity_arbitrator -> surgical_stylist -> END
        """
        workflow = StateGraph(dict)
        workflow.add_node("schema_repairer", self.schema_repairer_node)
        workflow.add_node("continuity_arbitrator", self.continuity_arbitrator_node)
        workflow.add_node("surgical_stylist", self.surgical_stylist_node)
        workflow.set_entry_point("schema_repairer")
        workflow.add_edge("schema_repairer", "continuity_arbitrator")
        workflow.add_edge("continuity_arbitrator", "surgical_stylist")
        workflow.add_edge("surgical_stylist", END)
        return workflow.compile()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_json(self, text: str) -> Any:
        """Extract and parse a JSON value from raw LLM response text.

        Strategy 1 — markdown code fence (```json ... ``` or ``` ... ```):
            Handles the common pattern where the LLM wraps its JSON in a
            fenced code block, optionally preceded by conversational text.

        Strategy 2 — first JSON structure in the string:
            Locates the first ``{`` or ``[`` character (whichever appears
            first) and attempts to parse from there to the matching close
            character found via ``rfind``.

        Args:
            text: Raw string from an LLM response.

        Returns:
            Parsed Python value (list, dict, str, int, …).

        Raises:
            ValueError: If no valid JSON can be extracted.
        """
        # Strategy 1: markdown code fence
        m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass  # fall through to strategy 2

        # Strategy 2: find the first JSON structure (object or array),
        # preferring whichever start character appears earliest in the string.
        candidates: list[tuple[int, str, str]] = []
        for start_char, close_char in [("{", "}"), ("[", "]")]:
            idx = text.find(start_char)
            if idx != -1:
                candidates.append((idx, start_char, close_char))

        for _, start_char, close_char in sorted(candidates):
            idx = text.find(start_char)
            end_idx = text.rfind(close_char)
            if end_idx <= idx:
                continue
            try:
                return json.loads(text[idx : end_idx + 1])
            except json.JSONDecodeError:
                continue

        raise ValueError(f"No valid JSON found in response: {text[:100]!r}")

    # ------------------------------------------------------------------
    # Genesis Resolver nodes
    # ------------------------------------------------------------------

    def schema_repairer_node(self, state: dict) -> dict:
        """Parse and repair the raw LLM response in state['last_raw_response'].

        When active_node is a recognised mutation node (per NODE_STATE_KEY_MAP),
        the parsed JSON array is converted to a dict keyed by 'target_id'.

        Args:
            state: Pipeline state dict. Expected keys:
                ``last_raw_response`` (str) — raw text from the LLM.
                ``active_node`` (str) — node that produced the response.

        Returns:
            On success::

                {
                    '<state_key>': <parsed and transformed value>,
                    'schema_repair_status': 'OK'
                }

            On failure::

                {
                    'schema_repair_status': 'FAILED',
                    'schema_repair_error': '<message>'
                }
        """
        raw = state.get("last_raw_response", "")
        active_node = state.get("active_node", "")

        try:
            parsed = self._extract_json(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            return {
                "schema_repair_status": "FAILED",
                "schema_repair_error": str(exc),
            }

        state_key = self.NODE_STATE_KEY_MAP.get(active_node, "parsed_response")

        # For mutation nodes: convert list → dict keyed by target_id
        if active_node in self.NODE_STATE_KEY_MAP and isinstance(parsed, list):
            try:
                transformed: dict[str, Any] = {item["target_id"]: item for item in parsed}
            except (KeyError, TypeError) as exc:
                return {
                    "schema_repair_status": "FAILED",
                    "schema_repair_error": f"Could not key mutations by target_id: {exc}",
                }
            return {state_key: transformed, "schema_repair_status": "OK"}

        return {state_key: parsed, "schema_repair_status": "OK"}

    def continuity_arbitrator_node(self, state: dict) -> dict:
        """Enforce NSE violations as hard overrides on craft verdicts.

        If NSE violations exist but the craft verdict is "CLEAN", this node
        upgrades the verdict to "REVISION RECOMMENDED" and appends a note
        to craft_symptoms. If violations are absent, or the verdict is
        already elevated, no changes are made.

        Args:
            state: Pipeline state dict. Expected keys:
                ``nse_violations`` (list[str]) — NSE constraint violations.
                ``craft_symptoms`` (str) — prose quality observations.
                ``craft_verdict`` (str) — "CLEAN", "REVISION RECOMMENDED",
                or "MAJOR REVISION".

        Returns:
            Partial state update dict, or ``{}`` if no changes are needed.
        """
        violations: list[str] = state.get("nse_violations", [])
        verdict: str = state.get("craft_verdict", "CLEAN")

        if not violations or verdict != "CLEAN":
            return {}

        count = len(violations)
        symptoms = state.get("craft_symptoms", "")
        override_note = f"[NSE OVERRIDE] {count} violation(s) detected."
        updated_symptoms = f"{symptoms} {override_note}".strip()

        return {
            "craft_verdict": "REVISION RECOMMENDED",
            "craft_symptoms": updated_symptoms,
        }

    def surgical_stylist_node(self, state: dict) -> dict:
        """Stub: pass scene draft through as the final scene.

        In a full implementation this node calls the LLM with a targeted
        editing prompt focused on craft_symptoms. Currently a passthrough.

        Args:
            state: Pipeline state dict. Expected key:
                ``scene_draft`` (str) — raw scene text to be refined.

        Returns:
            ``{'final_scene': <scene_draft>}``
        """
        return {"final_scene": state.get("scene_draft", "")}


# ---------------------------------------------------------------------------
# Embedded test runner
# ---------------------------------------------------------------------------


def run_internal_unit_tests(api_key: str) -> bool:
    """Run embedded Genesis Resolver validation tests.

    Instantiates LangGraphNovelGenesis and exercises two critical behaviours:
      1. Schema Repairer — JSON extraction from a malformed LLM response.
      2. Continuity Arbitrator — verdict escalation on NSE violations.

    No LLM calls are made; the tests are fully deterministic.

    Args:
        api_key: Passed to the pipeline constructor (not used during tests).

    Returns:
        True if all tests pass, False otherwise.
    """
    print("\n" + "=" * 60)
    print(" RUNNING GENESIS RESOLVER VALIDATION")
    print("=" * 60)

    pipeline = LangGraphNovelGenesis(api_key=api_key)
    passed = 0
    failed = 0

    # --- Test 1: Schema Repairer ---
    malformed = (
        "Analysis complete. ```json\n"
        '[{"mutation_type": "ADD_NODE", "target_id": "test_node"}]\n'
        "```"
    )
    repair_result = pipeline.schema_repairer_node(
        {"active_node": "nse_mutation", "last_raw_response": malformed}
    )
    if "nse_mutations" in repair_result and "test_node" in repair_result["nse_mutations"]:
        print("[PASS] Schema Repairer: Successfully sanitized malformed JSON.")
        passed += 1
    else:
        print("[FAIL] Schema Repairer: Failed to extract JSON from preamble.")
        failed += 1

    # --- Test 2: Continuity Arbitrator ---
    arb_result = pipeline.continuity_arbitrator_node(
        {
            "nse_violations": ["V1 KNOWLEDGE VIOLATION: char_01 acting on info_05"],
            "craft_symptoms": "Minor pacing issue.",
            "craft_verdict": "CLEAN",
        }
    )
    if arb_result.get("craft_verdict") == "REVISION RECOMMENDED":
        print("[PASS] Continuity Arbitrator: Correctly escalated NSE violation.")
        passed += 1
    else:
        print("[FAIL] Continuity Arbitrator: Failed to override 'CLEAN' verdict.")
        failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os

    parser = argparse.ArgumentParser(
        description="Novel Genesis Pipeline — LangGraph-based novel generation."
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OPENAI_API_KEY", ""),
        help="OpenAI-compatible API key (default: $OPENAI_API_KEY).",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run Genesis Resolver validation suite and exit.",
    )
    parser.add_argument(
        "--scenes",
        type=int,
        default=30,
        help="Number of scenes to generate (default: 30).",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="",
        help="Novel premise / opening prompt.",
    )
    args = parser.parse_args()

    if args.run_tests:
        success = run_internal_unit_tests(api_key=args.api_key)
        sys.exit(0 if success else 1)

    print(f"Novel Genesis Pipeline: {args.scenes} scenes queued.")
    print("Full pipeline execution not yet implemented. Use --run-tests to validate the Genesis Resolver.")
    sys.exit(0)
