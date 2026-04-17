"""
lat search — full-text search across the knowledge graph.
"""

from dataclasses import dataclass
from pathlib import Path

from ..graph import KnowledgeGraph


@dataclass
class SearchHit:
    section_id: str
    file: str
    title: str
    score: int
    snippet: str


def search(root: Path, query: str) -> list:
    """Return list[SearchHit] sorted by descending score."""
    graph = KnowledgeGraph.load(root)
    terms = query.lower().split()
    if not terms:
        return []

    hits = []
    for sec in graph.sections.values():
        score = _score(sec, terms)
        if score > 0:
            hits.append(SearchHit(
                section_id=sec.id,
                file=sec.file,
                title=sec.title,
                score=score,
                snippet=_snippet(sec.body, terms),
            ))

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits


def _score(sec, terms: list) -> int:
    score = 0
    id_lower    = sec.id.lower()
    title_lower = sec.title.lower()
    body_lower  = sec.body.lower()
    links_lower = " ".join(sec.wiki_links).lower()

    for term in terms:
        if term in id_lower:
            score += 10
        if term in title_lower:
            score += 8
        if term in links_lower:
            score += 4
        # Body occurrences: +2 each, capped at 6
        body_count = body_lower.count(term)
        score += min(body_count * 2, 6)

    return score


def _snippet(body: str, terms: list) -> str:
    """Return first 200-char window of body containing a query term."""
    lower = body.lower()
    for term in terms:
        idx = lower.find(term)
        if idx != -1:
            start = max(0, idx - 40)
            end   = min(len(body), start + 200)
            fragment = body[start:end].strip()
            if start > 0:
                fragment = "..." + fragment
            if end < len(body):
                fragment = fragment + "..."
            return fragment
    return body[:200].strip()


def print_results(hits: list) -> None:
    if not hits:
        print("No results found.")
        return
    for h in hits:
        print(f"\n[{h.section_id}] {h.file} — {h.title}")
        if h.snippet:
            print(f"  {h.snippet}")
