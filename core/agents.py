import os
import json
from datetime import datetime
from openai import OpenAI
from typing import Dict, Any, List

def _get_client() -> OpenAI:
    """Lazy client instantiation so import doesn't fail if OPENAI_API_KEY is not yet set."""
    return OpenAI()


class DeconstructorAgent:
    """
    The deterministic parser. It reads raw text and converts it into a
    strict JSON graph topology. It is forbidden from hallucinating or summarizing.
    """

    SYSTEM_PROMPT = """
    You are a deterministic Knowledge Graph Extraction Engine. Your ONLY purpose is to read unstructured text and map it to a strict JSON topology.

    CRITICAL DIRECTIVES:
    1. Zero Inference: Extract ONLY what is explicitly stated in the text. Do not summarize.
    2. Granularity: Break complex sentences down into isolated `nodes` and directional `edges`.
    3. Allowed Edge Types: You may ONLY use: REQUIRES, BLOCKS, PRODUCES, MODIFIES, CONTRADICTS, RELATES_TO.

    OUTPUT FORMAT: Valid JSON only matching this schema:
    {
      "nodes": [{"id": "unique_string", "label": "Concept/System/Deadline", "name": "Human Readable Name"}],
      "edges": [{"source_id": "unique_string", "target_id": "unique_string", "relationship": "REQUIRES"}]
    }
    """

    @staticmethod
    def extract_topology(text_chunk: str) -> Dict[str, Any]:
        """
        Sends the text to the LLM and forces a JSON return.
        """
        try:
            response = _get_client().chat.completions.create(
                model="gpt-4o-mini",  # Fast, cheap, and reliable for deterministic JSON extraction
                response_format={"type": "json_object"},
                temperature=0.0,  # CRITICAL: 0.0 makes the AI deterministic. No creative deviations allowed.
                messages=[
                    {"role": "system", "content": DeconstructorAgent.SYSTEM_PROMPT},
                    {"role": "user", "content": f"Extract graph topology from the following text:\n\n{text_chunk}"}
                ]
            )

            # Parse the JSON string back into a Python dictionary
            raw_json = response.choices[0].message.content
            return json.loads(raw_json)

        except Exception as e:
            print(f"[!] Deconstructor Agent Failed: {e}")
            # If the LLM fails, return empty topology so the Orchestrator doesn't crash
            return {"nodes": [], "edges": []}


class ContradictionHunterAgent:
    """
    The stress tester. It first verifies whether a structural conflict is a genuine
    logical paradox, then synthesizes a mitigation only for confirmed conflicts.
    """

    SYSTEM_PROMPT = """
    You are a Senior Risk Architect reviewing a potential structural vulnerability in an operational knowledge graph.

    You will be given:
    1. A TOPOLOGICAL PATTERN: Node A REQUIRES Node B, but Node C BLOCKS Node B.
    2. THE SOURCE TEXT: The raw document passages that produced these relationships.

    YOUR TASK — Two mandatory steps:

    STEP 1 — VERIFY: Is this a genuine operational paradox?
    Ask yourself: do the source passages actually describe a situation where the BLOCKS relationship meaningfully prevents the REQUIRES relationship from being satisfied?
    A conflict is SPURIOUS if:
    - The two passages come from unrelated contexts and do not logically interact.
    - The BLOCKS relationship is metaphorical, aspirational, or conditional rather than direct.
    - The conflict is trivially resolved by normal sequencing (e.g., do A before B).
    - The same concept appears under different names with no real tension.

    STEP 2 — SYNTHESIZE (only if genuine): If the conflict is real, provide a specific, actionable mitigation grounded in the source text. Be direct and unsparing. No generic corporate jargon.

    Respond ONLY with valid JSON in exactly this format:
    {
      "is_genuine": true or false,
      "confidence": a float between 0.0 and 1.0,
      "analysis": "Your mitigation if genuine, or a one-sentence explanation of why it is spurious.",
      "severity": an integer from 1 (minor nuisance) to 5 (programme-ending failure),
      "probability": an integer from 1 (highly unlikely to materialise) to 5 (virtually certain)
    }

    Severity and probability must always be present. For spurious conflicts, use 1 for both.
    """

    @staticmethod
    def synthesize_mitigation(structural_clash: str, source_text: str) -> Dict[str, Any]:
        """
        Verifies and analyses a structural conflict. Returns a dict with
        is_genuine, confidence, and analysis fields.
        """
        prompt_payload = f"""
        THE TOPOLOGICAL PATTERN:
        {structural_clash}

        THE SOURCE PROVENANCE (RAW TEXT):
        {source_text}
        """

        try:
            response = _get_client().chat.completions.create(
                model="gpt-4o",
                temperature=0.1,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": ContradictionHunterAgent.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt_payload}
                ]
            )

            return json.loads(response.choices[0].message.content)

        except Exception as e:
            print(f"[!] Contradiction Hunter Failed: {e}")
            return {"is_genuine": False, "confidence": 0.0, "analysis": "Error during verification.", "severity": 1, "probability": 1}


class FragilityAgent:
    """
    The Professional Skeptic. Verifies hub node fragility and produces
    a cascade collapse analysis for confirmed single points of failure.
    """

    SYSTEM_PROMPT = """
You are a Professional Skeptic and Risk Architect reviewing a knowledge graph for structural fragility.

You will be given:
1. A HUB NODE: a concept that multiple other nodes explicitly depend on.
2. ITS DEPENDENTS: the nodes that require it.
3. THE SOURCE TEXT: the raw document passage that produced this node.

YOUR TASK — Two mandatory steps:

STEP 1 — VERIFY: Is this a genuine single point of failure?
A hub node is SPURIOUS if:
- It is a generic concept (e.g. "process", "system", "team") that appears frequently as boilerplate.
- The dependents are from unrelated contexts and do not logically share this dependency.
- The dependency is merely administrative or nominal, not operational.

STEP 2 — ANALYSE (only if genuine): Describe the cascade collapse. What fails, in what order, and why does it matter operationally? Be specific and unsparing.

Respond ONLY with valid JSON in exactly this format:
{
  "is_genuine": true or false,
  "confidence": a float between 0.0 and 1.0,
  "cascade_nodes": ["node name 1", "node name 2"],
  "insight": "Your cascade analysis if genuine, or a one-sentence explanation of why it is spurious."
}
"""

    @staticmethod
    def analyse(hub_name: str, dependent_names: List[str], source_text: str) -> Dict[str, Any]:
        """
        Verifies whether a hub node is a genuine single point of failure and,
        if so, produces a cascade analysis.
        """
        prompt_payload = f"""
HUB NODE: {hub_name}

ITS DEPENDENTS:
{chr(10).join(f'- {name}' for name in dependent_names)}

THE SOURCE TEXT:
{source_text}
"""
        try:
            response = _get_client().chat.completions.create(
                model="gpt-4o",
                temperature=0.1,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": FragilityAgent.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt_payload}
                ]
            )
            return json.loads(response.choices[0].message.content)

        except Exception as e:
            print(f"[!] Fragility Agent Failed: {e}")
            return {"is_genuine": False, "confidence": 0.0, "cascade_nodes": [], "insight": "Error during analysis."}


class ChronosAgent:
    """
    The Temporal Normalization Engine.
    Reads raw text, anchors relative time to the current date,
    and outputs ISO 8601 date data for existing nodes only.
    """

    @staticmethod
    def get_system_prompt(anchor_date: str) -> str:
        """Returns the system prompt with anchor_date injected as the temporal baseline."""
        return f"""You are a deterministic Temporal Data Extraction Engine.
Your ONLY purpose is to read unstructured text, identify time-based constraints, and map them to strict JSON.

CRITICAL DIRECTIVES:
1. The absolute baseline date for this document is {anchor_date}.
2. Convert all relative terms ("next quarter", "in six months") into absolute ISO 8601 dates (YYYY-MM-DD) based on the baseline.
3. If a duration is mentioned (e.g., "a 4-week sprint"), calculate duration_days.
4. Identify if the node is a point-in-time (is_milestone: true) or a span (is_milestone: false).

OUTPUT FORMAT: Valid JSON only matching this schema:
{{
    "temporal_nodes": [
        {{
            "node_id": "exact_string_from_deconstructor",
            "start_date": "YYYY-MM-DD",
            "end_date": "YYYY-MM-DD",
            "duration_days": integer,
            "is_milestone": boolean
        }}
    ],
    "temporal_edges": [
        {{
            "source_id": "unique_string",
            "target_id": "unique_string",
            "relationship": "STARTS_AFTER"
        }}
    ]
}}

For STARTS_AFTER: source_id is the predecessor (the task that must finish first); target_id is the successor (the task constrained to start after the predecessor ends)."""

    @staticmethod
    def extract_time_data(text_chunk: str, existing_nodes: List[str]) -> Dict[str, Any]:
        """
        Sends text to the LLM and forces ISO 8601 date extraction.
        Only assigns dates to the provided existing node IDs.
        Returns empty structure on failure.
        """
        current_anchor = datetime.now().strftime("%Y-%m-%d")

        context_payload = f"""Extract temporal data for the following text.
ONLY assign dates to these existing Node IDs: {existing_nodes}

RAW TEXT:
{text_chunk}"""

        try:
            response = _get_client().chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                temperature=0.0,
                messages=[
                    {"role": "system", "content": ChronosAgent.get_system_prompt(current_anchor)},
                    {"role": "user", "content": context_payload}
                ]
            )
            return json.loads(response.choices[0].message.content)

        except Exception as e:
            print(f"[!] Chronos Agent Failed: {e}")
            return {"temporal_nodes": [], "temporal_edges": []}
