import os
import json
from datetime import datetime
from openai import OpenAI
from typing import Dict, Any, List
import numpy as np

def _get_client() -> OpenAI:
    """Returns an OpenAI-compatible client for the configured provider.

    Environment variables:
        LLM_PROVIDER          "openai" (default) or "openrouter"
        OPENAI_API_KEY        Required when LLM_PROVIDER=openai
        OPENROUTER_API_KEY    Required when LLM_PROVIDER=openrouter
    """
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    if provider == "openrouter":
        return OpenAI(
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            base_url="https://openrouter.ai/api/v1",
        )
    return OpenAI()


def _get_model(tier: str) -> str:
    """Returns the model name for the active provider and tier.

    Tiers:
        "fast"   — cheap, deterministic JSON extraction (DeconstructorAgent, ChronosAgent)
        "smart"  — higher-reasoning analysis (ContradictionHunterAgent, FragilityAgent)

    Override with environment variables:
        FAST_MODEL    e.g. "openai/gpt-4o-mini"  or "gpt-4o-mini"
        SMART_MODEL   e.g. "openai/gpt-4o"        or "anthropic/claude-3-5-sonnet"
    """
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    defaults = {
        "openai":     {"fast": "gpt-4o-mini",       "smart": "gpt-4o"},
        "openrouter": {"fast": "openai/gpt-4o-mini", "smart": "openai/gpt-4o"},
    }
    default = defaults.get(provider, defaults["openai"])[tier]
    env_key = "FAST_MODEL" if tier == "fast" else "SMART_MODEL"
    return os.environ.get(env_key, default)


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
                model=_get_model("fast"),  # Fast, cheap, and reliable for deterministic JSON extraction
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
                model=_get_model("smart"),
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
                model=_get_model("smart"),
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
                model=_get_model("fast"),
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


class StorytellerAgent:
    """
    Translates raw issue data into a plain-English executive report.
    Temperature 0.7 for natural prose. Returns a structured report_json dict.
    """

    SYSTEM_PROMPT = """You are an Executive Communication Specialist. Translate complex technical project risks into clear, plain-English summaries for senior business leaders who are not technical.

RULES:
1. Never use technical terms (no "node", "edge", "graph", "centrality", "vector", "contradiction").
2. Express every issue as a business consequence (cost, compliance, delay, dependency).
3. Use "issue" not "paradox" or "diamond".
4. Return ONLY valid JSON matching the schema below. No markdown, no preamble.

OUTPUT SCHEMA:
{
  "overall_assessment": "No Issues Found | Low Risk | Moderate Risk | High Risk | Critical Risk",
  "generated_at": "<ISO 8601 UTC timestamp>",
  "summary_narrative": "<2-3 sentence plain-English overview>",
  "business_impact": "<plain-English What This Means For You paragraph — mention specific business risks>",
  "issues": [
    {
      "severity": "critical | high | medium | low",
      "title": "<short plain-English title, max 10 words>",
      "plain_english": "<plain-English description of the problem and its business consequence>",
      "solution": "<plain-English recommended fix>",
      "source_nodes": ["<node_id>"]
    }
  ],
  "coverage_verified": true,
  "coverage_warning": null
}

Order issues: critical first, then high, then medium, then low."""

    def __init__(self):
        self.model = _get_model("smart")

    def run(self, raw_issues: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates a plain-English report from raw issue data.
        Returns immediately with a minimal report if no issues exist.
        """
        all_issues = (
            raw_issues.get("friction_lines", [])
            + raw_issues.get("chronological_friction_lines", [])
            + raw_issues.get("hub_vulnerabilities", [])
            + raw_issues.get("risk_matrix", [])
        )

        if not all_issues:
            return {
                "overall_assessment": "No Issues Found",
                "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "summary_narrative": "No conflicts or risks were detected in this document.",
                "business_impact": "",
                "issues": [],
                "coverage_verified": True,
                "coverage_warning": None,
            }

        # Stage 0 — deterministic hard-stop injection
        critical = [
            i for i in all_issues
            if isinstance(i.get("severity"), int) and i["severity"] >= 5
        ]
        must_include_block = ""
        if critical:
            must_include_block = "\n\nMUST INCLUDE (these issues are mandatory — do not omit them):\n"
            must_include_block += json.dumps(critical, indent=2)

        user_prompt = (
            f"Here is the complete list of issues detected in this document:\n\n"
            f"{json.dumps(raw_issues, indent=2)}"
            f"{must_include_block}"
        )

        client = _get_client()
        response = client.chat.completions.create(
            model=self.model,
            temperature=0.7,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        return json.loads(response.choices[0].message.content)


class CriticAgent:
    """
    Audits a draft report against the raw issue list.
    Finds omissions and triggers Storyteller revision (max 2 retries).
    Temperature 0.0 for deterministic auditing.
    """

    SYSTEM_PROMPT = """You are a meticulous audit specialist. You will be given:
1. A draft executive report (JSON)
2. A complete list of raw issues (JSON array)

Your ONLY job: identify raw issues that have NO representation in the draft report's issues array.

Return a JSON array of missing raw issues. If nothing is missing, return an empty array: []
Return ONLY valid JSON. No markdown, no explanation."""

    MAX_RETRIES = 2

    def run(
        self,
        draft: Dict[str, Any],
        raw_issues: Dict[str, Any],
        storyteller: Any = None,
    ) -> Dict[str, Any]:
        """
        Compares draft against raw_issues. Triggers Storyteller revision if gaps found.
        After MAX_RETRIES, appends a coverage_warning to the report instead of failing.
        """
        if storyteller is None:
            storyteller = StorytellerAgent()

        client = _get_client()
        current_draft = draft
        all_raw = (
            raw_issues.get("friction_lines", [])
            + raw_issues.get("chronological_friction_lines", [])
            + raw_issues.get("hub_vulnerabilities", [])
            + raw_issues.get("risk_matrix", [])
        )

        for attempt in range(self.MAX_RETRIES):
            response = client.chat.completions.create(
                model=_get_model("fast"),
                temperature=0.0,
                # No response_format here — the Critic returns a bare JSON array ([])
                # and json_object mode forbids bare arrays.
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": (
                        f"Draft report:\n{json.dumps(current_draft, indent=2)}\n\n"
                        f"Complete raw issue list:\n{json.dumps(all_raw, indent=2)}"
                    )},
                ],
            )
            content = response.choices[0].message.content
            try:
                parsed = json.loads(content)
                # Model should return a bare array; handle any wrapping defensively
                if isinstance(parsed, list):
                    gaps = parsed
                elif isinstance(parsed, dict):
                    # Flatten any top-level list value regardless of key name
                    list_values = [v for v in parsed.values() if isinstance(v, list)]
                    gaps = list_values[0] if list_values else []
                else:
                    gaps = []
            except (json.JSONDecodeError, AttributeError):
                gaps = []

            if not gaps:
                return current_draft

            # Inject missing items and regenerate
            injected = dict(raw_issues)
            injected["_forced_inclusions"] = gaps
            current_draft = storyteller.run(injected)

        # Max retries exhausted — append warning and return
        current_draft["coverage_verified"] = False
        current_draft["coverage_warning"] = (
            "Note: the AI could not fully verify that all issues are represented in this report. "
            "Please cross-reference the Friction Queue for the complete technical list."
        )
        return current_draft


class KDECoverageCheck:
    """
    Verifies that the generated report semantically covers all source material.
    Uses cosine similarity gap detection with numpy — no API calls, no extra cost.

    For each source chunk embedding, finds the maximum cosine similarity to any
    output issue embedding. If any source chunk's max similarity is below the
    threshold, it is considered uncovered and a coverage_warning is appended.

    IMPORTANT: uses vault.collection._embedding_function — the same model used at
    ingestion time — so source and output embeddings are in the same vector space.
    """

    SIMILARITY_THRESHOLD = 0.25

    def __init__(self, vault: Any):
        self.vault = vault

    def check(self, document_id: str, report: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compares source chunk embeddings to output issue embeddings.
        Returns the report dict with coverage_verified and coverage_warning set.
        """
        # 1. Collect source_chunk_ids from edges and friction_lines for this document
        cursor = self.vault.conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT source_chunk_id FROM edges WHERE document_id = ?
            UNION
            SELECT DISTINCT provenance_ids FROM friction_lines WHERE document_id = ?
            """,
            (document_id, document_id)
        )
        rows = cursor.fetchall()
        source_chunk_ids = [r["source_chunk_id"] for r in rows if r["source_chunk_id"]]

        if not source_chunk_ids:
            report["coverage_verified"] = True
            report["coverage_warning"] = None
            return report

        # 2. Fetch source embeddings from ChromaDB
        chroma_result = self.vault.collection.get(
            ids=source_chunk_ids,
            include=["embeddings"]
        )
        source_embeddings = chroma_result.get("embeddings") or []
        if not source_embeddings:
            report["coverage_verified"] = True
            report["coverage_warning"] = None
            return report

        source_matrix = np.array(source_embeddings, dtype=np.float32)

        # 3. Embed report issue texts using the SAME embedding function as ingestion.
        #    vault.collection._embedding_function is the ChromaDB collection's own EF —
        #    guaranteed to be in the same vector space as the stored source embeddings.
        issue_texts = [
            i.get("plain_english", "") for i in report.get("issues", [])
            if i.get("plain_english")
        ]
        if not issue_texts:
            report["coverage_verified"] = False
            report["coverage_warning"] = (
                "Note: the AI could not fully verify that all issues are represented in this report. "
                "Please cross-reference the Friction Queue for the complete technical list."
            )
            return report

        ef = self.vault.collection._embedding_function
        output_embeddings = ef(issue_texts)
        output_matrix = np.array(output_embeddings, dtype=np.float32)

        # 4. Cosine similarity: normalise both matrices then compute dot product
        def _l2_norm(m: np.ndarray) -> np.ndarray:
            norms = np.linalg.norm(m, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1e-10, norms)
            return m / norms

        source_norm = _l2_norm(source_matrix)
        output_norm = _l2_norm(output_matrix)

        # similarity[i, j] = cosine similarity between source[i] and output[j]
        similarity = source_norm @ output_norm.T  # shape: (n_source, n_output)
        max_similarity_per_source = similarity.max(axis=1)  # shape: (n_source,)

        # 5. Flag if any source chunk is below threshold
        uncovered = np.sum(max_similarity_per_source < self.SIMILARITY_THRESHOLD)
        if uncovered > 0:
            report["coverage_verified"] = False
            report["coverage_warning"] = (
                "Note: the AI could not fully verify that all issues are represented in this report. "
                "Please cross-reference the Friction Queue for the complete technical list."
            )
        else:
            report["coverage_verified"] = True
            report["coverage_warning"] = None

        return report
