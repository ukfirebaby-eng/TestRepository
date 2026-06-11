import re

from core.accuracy.schemas import CanonicalEntity, ExtractedClaim


_TRAILING_ALIAS_WORDS = {
    "program",
    "programme",
    "project",
    "initiative",
    "workstream",
}

_GENERIC_ENTITY_WORDS = {
    "activity",
    "approval",
    "blocker",
    "condition",
    "date",
    "deadline",
    "dependency",
    "deliverable",
    "document",
    "evidence",
    "gate",
    "initiative",
    "item",
    "milestone",
    "plan",
    "prerequisite",
    "process",
    "program",
    "programme",
    "project",
    "requirement",
    "schedule",
    "stage",
    "task",
    "testing",
    "thing",
    "work",
    "workstream",
}

_GENERIC_ENTITY_PRONOUNS = {
    "he",
    "her",
    "him",
    "his",
    "it",
    "its",
    "she",
    "that",
    "their",
    "them",
    "these",
    "they",
    "this",
    "those",
}


def _tokens(name: str) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    tokens = [token for token in cleaned.split() if token]
    while tokens and tokens[0] in {"a", "an", "the"}:
        tokens.pop(0)
    while len(tokens) > 1 and tokens[-1] in _TRAILING_ALIAS_WORDS:
        tokens.pop()
    return tokens


def _display_tokens(name: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9]+", name.strip())
    while tokens and tokens[0].lower() in {"a", "an", "the"}:
        tokens.pop(0)
    while len(tokens) > 1 and tokens[-1].lower() in _TRAILING_ALIAS_WORDS:
        tokens.pop()
    return tokens


def canonical_entity_name(name: str) -> str:
    tokens = _display_tokens(name)
    if not tokens:
        return "Unknown"
    return " ".join(token if token.isupper() else token.capitalize() for token in tokens)


def canonical_entity_id(name: str) -> str:
    tokens = _tokens(name)
    slug = "_".join(tokens) or "unknown"
    return f"entity_{slug}"


def is_generic_entity_name(name: str) -> bool:
    tokens = _tokens(name)
    if not tokens:
        return True
    generic_terms = _GENERIC_ENTITY_WORDS | _GENERIC_ENTITY_PRONOUNS
    if len(tokens) == 1 and tokens[0] in generic_terms:
        return True
    return all(token in generic_terms for token in tokens)


def _infer_entity_type(name: str) -> str:
    normalized = " ".join(_tokens(name))
    if any(term in normalized for term in ["api", "gateway", "database", "module", "service", "system", "platform"]):
        return "system"
    if any(term in normalized for term in ["deadline", "milestone", "date"]):
        return "deadline"
    if any(term in normalized for term in ["team", "board", "committee"]):
        return "team"
    if any(term in normalized for term in ["risk", "issue", "threat"]):
        return "risk"
    if any(term in normalized for term in ["deliverable", "pack", "report"]):
        return "deliverable"
    return "initiative"


def build_canonical_entities_from_claims(claims: list[ExtractedClaim]) -> list[CanonicalEntity]:
    grouped: dict[str, dict] = {}
    for claim in claims:
        for raw_name in [claim.subject, claim.object]:
            entity_id = canonical_entity_id(raw_name)
            if entity_id not in grouped:
                grouped[entity_id] = {
                    "canonical_name": canonical_entity_name(raw_name),
                    "entity_type": _infer_entity_type(raw_name),
                    "aliases": [],
                    "source_span_ids": [],
                    "confidence": claim.confidence,
                }
            entity = grouped[entity_id]
            if raw_name not in entity["aliases"]:
                entity["aliases"].append(raw_name)
            for span_id in claim.evidence_span_ids:
                if span_id not in entity["source_span_ids"]:
                    entity["source_span_ids"].append(span_id)
            entity["confidence"] = max(entity["confidence"], claim.confidence)

    return [
        CanonicalEntity(
            entity_id=entity_id,
            canonical_name=data["canonical_name"],
            entity_type=data["entity_type"],
            aliases=data["aliases"],
            source_span_ids=data["source_span_ids"],
            confidence=data["confidence"],
        )
        for entity_id, data in sorted(grouped.items())
    ]
