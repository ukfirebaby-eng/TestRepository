"""
novel_genesis_pipeline.py — Novel Genesis System: LangGraph orchestration pipeline.

Defines:
  PipelineState           — TypedDict shared between all graph nodes
  NovelGenesisPipeline    — concrete pipeline class; wires the LangGraph DAG

Phase J.2 patch (generate_intent)
-----------------------------------
The generate_intent node has been augmented with a Cognitive Overload Precheck
that loads a pre-trained Random Forest classifier and emits a warn-level log
entry when the predicted probability of audit failure exceeds
``config.overload_threshold`` (default 0.60).

The precheck is strictly additive:
  • When cognitive_overload_model.pkl is absent → skipped silently.
  • When nse/nse_graph.json is absent → skipped silently.
  • On any exception (including missing joblib) → logged at 'info', not 'err'.
  • self._call_agent() is ALWAYS invoked regardless of prediction outcome.
"""

from __future__ import annotations

from pathlib import Path
from statistics import mean
from typing import Any, Optional, TypedDict

from ngs_base import NGSBaseTool, NGSConfig
from nse_graph import NSEGraph, deserialise_nse


# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------

class PipelineState(TypedDict, total=False):
    """Shared state dict passed between every LangGraph node."""
    scene_num: int
    outline_segment: str
    nse_snapshot: str          # serialised NSE summary injected into prompts
    nse_state: str             # alias used by some nodes
    scene_intent: str
    draft_prose: str
    revised_prose: str
    audit_verdict: str
    voice_audit_verdict: str
    beta_report: str
    revision_pass: int


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class NovelGenesisPipeline(NGSBaseTool):
    """Novel Genesis LangGraph pipeline.

    Nodes (in execution order):
      load_outline        — reads the chapter outline from disk
      nse_snapshot_node   — serialises current NSE graph into a text summary
      generate_intent     — (J.2 patched) generates scene structural intent
      generate_prose      — writes raw draft prose
      craft_audit_node    — evaluates prose against craft rubric
      voice_audit_node    — evaluates prose against voice rubric
      revision_node       — rewrites prose based on audit feedback
      finalize_scene      — saves the accepted prose to scenes/
      nse_mutation_node   — applies NSE graph mutations from the new scene
      beta_reader_node    — (every beta_interval scenes) generates beta report
    """

    def __init__(self, config: Optional[NGSConfig] = None) -> None:
        super().__init__(config or NGSConfig())

    # ------------------------------------------------------------------
    # ── J.2: generate_intent (patched) ──────────────────────────────
    # ------------------------------------------------------------------

    def generate_intent(self, state: PipelineState) -> dict[str, Any]:
        """Generate the structural intent for the upcoming scene.

        Phase J.2 Cognitive Overload Precheck
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        Before invoking the LLM, this node attempts to load
        ``cognitive_overload_model.pkl`` and measure live graph complexity.
        If the predicted probability of audit failure meets or exceeds
        ``config.overload_threshold``, a warn-level entry is emitted to the
        terminal and ngs_run.jsonl.

        The standard ``_call_agent()`` call always executes regardless of the
        prediction outcome — the model warns, it does not gate.
        """

        # ── J.2: Cognitive Overload Precheck ─────────────────────────
        model_path = Path("cognitive_overload_model.pkl")
        graph_path = self.output_dir / "nse" / "nse_graph.json"
        overload_threshold = getattr(self.config, "overload_threshold", 0.60)

        if model_path.exists() and graph_path.exists():
            try:
                import joblib

                clf = joblib.load(model_path)
                graph: NSEGraph = deserialise_nse(graph_path)
                rels = list(graph.relationships.values())
                features = [[
                    len(graph.characters),
                    sum(
                        1 for i in graph.information.values()
                        if i.revealed_at_scene is None
                    ),
                    mean([r.tension_level for r in rels]) if rels else 0.0,
                    mean([r.trust_level for r in rels]) if rels else 0.0,
                    sum(1 for e in graph.events.values() if not e.occurred),
                ]]
                prob: float = clf.predict_proba(features)[0][1]

                if prob >= overload_threshold:
                    f = features[0]
                    self._log(
                        f"COGNITIVE OVERLOAD RISK: {prob:.0%} probability of audit"
                        f" failure."
                        f" Graph state: [chars={f[0]}, secrets={f[1]},"
                        f" tension={f[2]:.2f}, trust={f[3]:.2f},"
                        f" pending={f[4]}].",
                        "warn",
                        node="generate_intent",
                    )
            except Exception as exc:
                self._log(
                    f"J.2 precheck skipped: {exc}",
                    "info",
                    node="generate_intent",
                )
        # ── End J.2 precheck ─────────────────────────────────────────

        # Standard intent generation (unchanged)
        nse_context = state.get("nse_snapshot") or state.get("nse_state", "")
        content = self._call_agent(
            self.structural_llm,
            self.prompts.get("scene_intent", "Generate scene intent."),
            f"Outline:\n{state.get('outline_segment', '')}\nNSE state:\n{nse_context}",
            f"Scene {state.get('scene_num', '?')} Intent",
        )
        self._save(f"nse/scene_{state.get('scene_num', 0):02d}_intent.md", content)
        return {"scene_intent": content}

    # ------------------------------------------------------------------
    # Remaining nodes (stubs — to be fully implemented in later phases)
    # ------------------------------------------------------------------

    def load_outline(self, state: PipelineState) -> dict[str, Any]:
        """Load the next outline segment for the upcoming scene."""
        raise NotImplementedError

    def nse_snapshot_node(self, state: PipelineState) -> dict[str, Any]:
        """Serialise the current NSE graph state into a prompt-friendly summary."""
        raise NotImplementedError

    def generate_prose(self, state: PipelineState) -> dict[str, Any]:
        """Generate raw draft prose from the scene intent."""
        raise NotImplementedError

    def craft_audit_node(self, state: PipelineState) -> dict[str, Any]:
        """Evaluate the draft prose against the craft rubric."""
        raise NotImplementedError

    def voice_audit_node(self, state: PipelineState) -> dict[str, Any]:
        """Evaluate the draft prose against the voice rubric."""
        raise NotImplementedError

    def revision_node(self, state: PipelineState) -> dict[str, Any]:
        """Rewrite prose based on audit feedback."""
        raise NotImplementedError

    def finalize_scene(self, state: PipelineState) -> dict[str, Any]:
        """Save the accepted prose to scenes/scene_NN.md."""
        raise NotImplementedError

    def nse_mutation_node(self, state: PipelineState) -> dict[str, Any]:
        """Apply NSE graph mutations derived from the newly generated scene."""
        raise NotImplementedError

    def beta_reader_node(self, state: PipelineState) -> dict[str, Any]:
        """Generate a simulated Beta Reader report (every beta_interval scenes)."""
        raise NotImplementedError
