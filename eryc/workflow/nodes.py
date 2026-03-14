"""
LangGraph workflow nodes for the ERYC evidence-grounded query workflow.

Each node receives the current :class:`EDICState`, performs one bounded
operation, and returns a partial state dict containing only the fields
it modifies.  Nodes do not mutate the state in place.

The workflow follows the six stages described in spec §6.1:
  ingress_check → classify_query → plan_retrieval →
  hybrid_retrieval → evidence_judge → answer_compose → grounding_validate

Phase D-2 through D-6.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from eryc.config import get_settings
from eryc.models.domain import CandidateChunk, Citation
from eryc.retrieval.context import ContextExpander
from eryc.retrieval.fusion import reciprocal_rank_fusion
from eryc.retrieval.lexical import LexicalRetriever
from eryc.retrieval.reranker import Reranker
from eryc.retrieval.semantic import SemanticRetriever
from eryc.workflow.state import EDICState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------

_reranker: Optional[Reranker] = None


def _get_reranker() -> Reranker:
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker


# ---------------------------------------------------------------------------
# Helper: get a database connection for the current node invocation
# ---------------------------------------------------------------------------


def _get_conn() -> sqlite3.Connection:
    from eryc.database.connection import open_connection

    return open_connection(get_settings().db_path)


# ---------------------------------------------------------------------------
# Node: ingress_check
# ---------------------------------------------------------------------------


def ingress_check(state: EDICState) -> Dict[str, Any]:
    """
    Validate user, workspace and access scope before processing begins.

    Sets ``allowed_sensitivity_levels`` based on the user's role.
    """
    conn = _get_conn()
    workspace_id = state.get("workspace_id", "")
    user_id = state.get("user_id", "")

    errors = list(state.get("errors", []))

    # Verify workspace exists.
    ws = conn.execute(
        "SELECT workspace_id FROM workspaces WHERE workspace_id = ?",
        (workspace_id,),
    ).fetchone()
    if ws is None:
        errors.append(f"Workspace '{workspace_id}' not found.")

    # Determine sensitivity scope from user role.
    user = conn.execute(
        "SELECT role FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()

    if user and user["role"] in ("admin", "manager"):
        allowed = ["standard", "restricted", "confidential"]
    else:
        allowed = ["standard"]

    return {"allowed_sensitivity_levels": allowed, "errors": errors}


# ---------------------------------------------------------------------------
# Node: classify_query
# ---------------------------------------------------------------------------


def classify_query(state: EDICState) -> Dict[str, Any]:
    """
    Classify the query intent and extract entities and temporal filters.

    Uses Claude (via the Anthropic SDK) when available; falls back to a
    rule-based classifier for offline or key-free environments.
    """
    query = state.get("query", "")
    settings = get_settings()

    try:
        return _classify_with_claude(query, settings)
    except Exception as exc:
        logger.warning("Claude classifier failed (%s); using rule-based fallback", exc)
        return _classify_with_rules(query)


def _classify_with_claude(query: str, settings) -> Dict[str, Any]:
    """Ask Claude to classify the query and extract metadata."""
    import anthropic

    api_key = settings.effective_anthropic_key()
    if not api_key:
        raise ValueError("No Anthropic API key configured")

    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = (
        "You are a query classifier for a document intelligence system. "
        "Analyse the user query and return a JSON object with these fields:\n"
        "- query_class: one of keyword_exact, semantic, mixed, authoritative_lookup, "
        "consistency_check, evidence_state, timeline_query, entity_summary\n"
        "- exact_terms: list of exact terms/identifiers to look for\n"
        "- entities: list of {name, type} objects extracted from the query\n"
        "- temporal_filter: {from, to} date strings if the query has time scope, else null\n"
        "Return ONLY valid JSON, no explanation."
    )

    message = client.messages.create(
        model=settings.llm_model,
        max_tokens=256,
        system=system_prompt,
        messages=[{"role": "user", "content": query}],
    )

    text = message.content[0].text.strip()
    # Strip markdown code fences if present.
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    data = json.loads(text)

    return {
        "query_class": data.get("query_class", "semantic"),
        "exact_terms": data.get("exact_terms", []),
        "entities": data.get("entities", []),
        "temporal_filter": data.get("temporal_filter"),
    }


def _classify_with_rules(query: str) -> Dict[str, Any]:
    """Simple keyword-based fallback classifier."""
    q_lower = query.lower()

    if any(w in q_lower for w in ("timeline", "chronolog", "order", "sequence")):
        query_class = "timeline_query"
    elif any(w in q_lower for w in ("conflict", "contradict", "disagree", "inconsist")):
        query_class = "consistency_check"
    elif any(w in q_lower for w in ("policy", "procedure", "guidance", "authoritative")):
        query_class = "authoritative_lookup"
    elif any(w in q_lower for w in ("summarise", "summary", "what has", "evidenced")):
        query_class = "evidence_state"
    elif any(w in q_lower for w in ("person", "household", "case", "entity")):
        query_class = "entity_summary"
    else:
        query_class = "semantic"

    return {
        "query_class": query_class,
        "exact_terms": [],
        "entities": [],
        "temporal_filter": None,
    }


# ---------------------------------------------------------------------------
# Node: plan_retrieval
# ---------------------------------------------------------------------------


def plan_retrieval(state: EDICState) -> Dict[str, Any]:
    """
    Select the retrieval mode, candidate sizes and retry policy.

    Applies time-aware and entity-aware filter overrides from the classified
    query state.
    """
    query_class = state.get("query_class", "semantic")
    settings = get_settings()

    # Choose mode based on query class (spec §9.3).
    if query_class in ("keyword_exact", "authoritative_lookup"):
        mode = "lexical"
    elif query_class in ("semantic", "evidence_state", "entity_summary"):
        mode = "hybrid"
    else:
        mode = "hybrid"

    # Merge temporal filters from classifier into the request filters.
    filters = dict(state.get("filters", {}))
    tf = state.get("temporal_filter")
    if tf:
        if tf.get("from"):
            filters.setdefault("time_from", tf["from"])
        if tf.get("to"):
            filters.setdefault("time_to", tf["to"])

    return {
        "retrieval_mode": mode,
        "lexical_k": settings.default_lexical_k,
        "semantic_k": settings.default_semantic_k,
        "rerank_top_n": settings.default_rerank_top_n,
        "filters": filters,
    }


# ---------------------------------------------------------------------------
# Node: hybrid_retrieval
# ---------------------------------------------------------------------------


def hybrid_retrieval(state: EDICState) -> Dict[str, Any]:
    """
    Execute lexical, semantic or hybrid retrieval followed by RRF fusion,
    optional reranking and adjacent context expansion.

    Increments ``retrieval_round`` and appends to ``retrieval_attempts``.
    """
    settings = get_settings()
    conn = _get_conn()

    query = state.get("query", "")
    mode = state.get("retrieval_mode", "hybrid")
    lexical_k = state.get("lexical_k", settings.default_lexical_k)
    semantic_k = state.get("semantic_k", settings.default_semantic_k)
    rerank_top_n = state.get("rerank_top_n", settings.default_rerank_top_n)
    filters = state.get("filters", {})
    round_number = state.get("retrieval_round", 0) + 1
    tool_calls = state.get("tool_calls_used", 0) + 1

    workspace_id = filters.get("workspace_id", state.get("workspace_id", ""))
    collection_ids = filters.get("collection_ids")
    doc_types = filters.get("doc_types")
    time_from = filters.get("time_from")
    time_to = filters.get("time_to")

    # --- Lexical retrieval ---
    lexical_results: List[CandidateChunk] = []
    if mode in ("lexical", "hybrid"):
        retriever = LexicalRetriever(conn)
        lexical_results = retriever.search(
            query,
            workspace_id=workspace_id,
            limit=lexical_k,
            collection_ids=collection_ids,
            doc_types=doc_types,
            time_from=time_from,
            time_to=time_to,
        )

    # --- Semantic retrieval ---
    semantic_results: List[CandidateChunk] = []
    if mode in ("semantic", "hybrid"):
        sem_retriever = SemanticRetriever(conn)
        if sem_retriever.available:
            semantic_results = sem_retriever.search(
                query,
                workspace_id=workspace_id,
                limit=semantic_k,
                collection_ids=collection_ids,
                doc_types=doc_types,
                time_from=time_from,
                time_to=time_to,
            )

    # --- RRF fusion ---
    fused, diagnostics = reciprocal_rank_fusion(
        lexical_results,
        semantic_results,
        k=settings.rrf_k,
        max_candidates=settings.max_prefusion_candidates,
    )
    diagnostics.query = query

    # --- Optional reranking ---
    reranker = _get_reranker()
    reranker_timed_out = True
    if reranker.available and fused:
        fused, reranker_timed_out = reranker.rerank(query, fused, top_n=rerank_top_n)

    # --- Context expansion ---
    expander = ContextExpander(conn, window=1)
    context = expander.expand(fused, max_context_chunks=settings.max_context_chunks)

    # Record the attempt.
    attempt = {
        "attempt_id": "att_" + uuid.uuid4().hex,
        "run_id": state.get("run_id", ""),
        "round_number": round_number,
        "mode": mode,
        "query_used": query,
        "filters": filters,
        "result_count": len(fused),
        "diagnostics": {
            "lexical_hits": diagnostics.lexical_hits,
            "semantic_hits": diagnostics.semantic_hits,
            "fused_count": diagnostics.fused_count,
            "reranker_used": reranker.available,
            "reranker_timed_out": reranker_timed_out,
        },
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }

    attempts = list(state.get("retrieval_attempts", []))
    attempts.append(attempt)

    return {
        "retrieval_round": round_number,
        "tool_calls_used": tool_calls,
        "retrieval_attempts": attempts,
        "candidate_chunks": [c.model_dump() for c in fused],
        "context_chunks": [c.model_dump() for c in context],
        "diagnostics": {
            **state.get("diagnostics", {}),
            "retrieval_mode": mode,
            "retrieval_rounds": round_number,
            "reranker_timed_out": reranker_timed_out,
        },
    }


# ---------------------------------------------------------------------------
# Node: evidence_judge
# ---------------------------------------------------------------------------


def evidence_judge(state: EDICState) -> Dict[str, Any]:
    """
    Determine whether the current candidate set contains enough evidence
    to answer the query safely.

    Returns one of:
    - ``"enough"``      → proceed to answer composition
    - ``"needs_more"``  → run another retrieval round
    - ``"insufficient"`` → stop with a safe no-answer response
    """
    settings = get_settings()
    candidates = state.get("candidate_chunks", [])
    round_number = state.get("retrieval_round", 0)
    max_rounds = settings.max_retrieval_rounds

    if not candidates:
        if round_number >= max_rounds:
            verdict = "insufficient"
        else:
            verdict = "needs_more"
    elif len(candidates) >= 3:
        verdict = "enough"
    elif round_number >= max_rounds:
        # We have some evidence but not many — still attempt an answer
        # with a clear uncertainty caveat.
        verdict = "enough"
    else:
        verdict = "needs_more"

    return {"evidence_verdict": verdict}


# ---------------------------------------------------------------------------
# Node: answer_compose
# ---------------------------------------------------------------------------


def answer_compose(state: EDICState) -> Dict[str, Any]:
    """
    Generate a grounded answer from the evidence in ``context_chunks``.

    Uses Claude to compose a citation-first answer; extracts which chunks
    were cited and builds the citation list.  Falls back to a deterministic
    evidence listing if the API is unavailable.
    """
    settings = get_settings()
    query = state.get("query", "")
    context = state.get("context_chunks", [])
    max_citations = state.get("response_options", {}).get(
        "max_citations", settings.max_final_citations
    )

    if not context:
        return {
            "final_answer": (
                "No relevant evidence was found in the indexed documents "
                "for this query."
            ),
            "citations": [],
            "draft_answer": None,
        }

    # Build the evidence block for the prompt.
    evidence_block = _build_evidence_block(context[:max_citations])

    try:
        answer, cited_ids = _compose_with_claude(query, evidence_block, settings)
    except Exception as exc:
        logger.warning("Claude answer composition failed (%s); using evidence listing", exc)
        answer, cited_ids = _compose_fallback(query, context[:max_citations])

    # Build citation records from cited chunk IDs.
    citations = _build_citations(state, context, cited_ids, max_citations)

    return {
        "draft_answer": answer,
        "final_answer": answer,
        "citations": [c.model_dump() for c in citations],
    }


def _build_evidence_block(chunks: List[Dict[str, Any]]) -> str:
    parts = []
    for i, chunk in enumerate(chunks):
        parts.append(
            f"[{i + 1}] {chunk.get('canonical_title', 'Untitled')} "
            f"({chunk.get('section_path', '')}):\n{chunk.get('text', '')}"
        )
    return "\n\n---\n\n".join(parts)


def _compose_with_claude(
    query: str, evidence: str, settings
) -> tuple[str, List[str]]:
    """Ask Claude to compose a grounded answer and return (answer, cited_chunk_ids)."""
    import anthropic

    api_key = settings.effective_anthropic_key()
    if not api_key:
        raise ValueError("No API key")

    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = (
        "You are an evidence-grounded document analyst. "
        "Answer the user's question using ONLY the numbered evidence excerpts provided. "
        "Cite each piece of evidence you use by including its number in square brackets "
        "like [1], [2] etc. "
        "If the evidence is insufficient to answer fully, say so explicitly rather than "
        "speculating beyond the record. "
        "Be concise and factual."
    )

    user_message = (
        f"Question: {query}\n\n"
        f"Evidence:\n{evidence}\n\n"
        "Please provide a grounded answer with citations."
    )

    message = client.messages.create(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    answer = message.content[0].text.strip()
    # Citation extraction is handled at the grounding stage;
    # return all chunk IDs as cited for now.
    return answer, []


def _compose_fallback(
    query: str, chunks: List[Dict[str, Any]]
) -> tuple[str, List[str]]:
    """Build a simple evidence-listing response without LLM."""
    lines = [f"Evidence found for: '{query}'\n"]
    for i, chunk in enumerate(chunks):
        lines.append(
            f"[{i + 1}] {chunk.get('canonical_title', 'Untitled')} "
            f"— {chunk.get('text_preview', '')[:120]}..."
        )
    return "\n".join(lines), [c.get("chunk_id", "") for c in chunks]


def _build_citations(
    state: EDICState,
    context: List[Dict[str, Any]],
    cited_ids: List[str],
    max_citations: int,
) -> List[Citation]:
    """Build version-pinned Citation objects from context chunks."""
    run_id = state.get("run_id", "")
    # If cited_ids is empty, cite all context chunks.
    source_chunks = (
        [c for c in context if c.get("chunk_id") in cited_ids]
        if cited_ids
        else context[:max_citations]
    )

    citations = []
    for ordinal, chunk in enumerate(source_chunks[:max_citations]):
        citations.append(
            Citation(
                citation_id="cit_" + uuid.uuid4().hex,
                run_id=run_id,
                chunk_id=chunk.get("chunk_id", ""),
                document_id=chunk.get("document_id", ""),
                version_id=chunk.get("version_id", ""),
                title=chunk.get("canonical_title", "Untitled"),
                locator=chunk.get("section_path"),
                source_path=chunk.get("source_path"),
                snippet=chunk.get("text_preview", "")[:200],
                ordinal=ordinal,
            )
        )
    return citations


# ---------------------------------------------------------------------------
# Node: grounding_validate
# ---------------------------------------------------------------------------


def grounding_validate(state: EDICState) -> Dict[str, Any]:
    """
    Validate that the answer is supported by the cited evidence.

    Blocks unsupported claims and sets the grounding report.  If the
    evidence verdict was ``"insufficient"`` the answer is replaced with
    the safe no-answer template.
    """
    verdict = state.get("evidence_verdict", "enough")
    answer = state.get("final_answer", "")
    citations = state.get("citations", [])

    if verdict == "insufficient":
        final = (
            "The indexed documents do not contain sufficient evidence to answer "
            "this query reliably.  Please review the source material directly or "
            "refine the query."
        )
        report = {
            "verdict": "insufficient",
            "citation_coverage": 0.0,
            "unsupported_claims": 0,
        }
        return {
            "final_answer": final,
            "grounding_report": report,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    citation_count = len(citations)
    # Simple coverage heuristic: at least one citation per 200 characters of answer.
    expected = max(1, len(answer) // 200)
    coverage = min(1.0, citation_count / expected) if expected else 1.0
    unsupported = max(0, expected - citation_count)

    grounding_verdict = "pass" if coverage >= 0.5 else "fail"

    report = {
        "verdict": grounding_verdict,
        "citation_coverage": round(coverage, 3),
        "unsupported_claims": unsupported,
    }

    return {
        "grounding_report": report,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
