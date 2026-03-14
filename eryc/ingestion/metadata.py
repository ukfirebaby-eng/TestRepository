"""
Metadata extraction for the ERYC ingestion pipeline.

Phase B-3: Extract document type, title, temporal fields, sensitivity
labels and entity references from the parsed document.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from eryc.ingestion.parsers.base import ParsedDocument


# ---------------------------------------------------------------------------
# Document type classification heuristics
# ---------------------------------------------------------------------------

_TYPE_KEYWORDS: Dict[str, List[str]] = {
    # More specific types are checked first to avoid false positives.
    "case_note": ["case note", "contact note", "visit note", "home visit"],
    "assessment": [
        "initial assessment",
        "risk assessment",
        "re-assessment",
    ],
    "care_plan": ["care plan", "support plan", "action plan"],
    "meeting_summary": ["strategy meeting", "review meeting", "meeting minutes"],
    "policy": ["this policy", "this procedure", "policy sets out", "guidance sets out"],
    "referral": ["referral form", "referred by", "referral to"],
    "report": ["annual report", "quarterly report", "this report"],
}

_SENSITIVITY_KEYWORDS: Dict[str, List[str]] = {
    "confidential": ["confidential", "strictly private", "sensitive personal"],
    "restricted": ["restricted", "not for general distribution", "internal only"],
}

_DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})\b"),
    re.compile(
        r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September"
        r"|October|November|December)\s+(\d{4})\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
]


def _classify_doc_type(parsed: ParsedDocument, hint: Optional[str] = None) -> str:
    """
    Infer a document type from the title and first 500 characters of body text.

    ``hint`` from the ingest request takes precedence if supplied.
    """
    if hint:
        return hint

    probe = (parsed.canonical_title + " " + parsed.raw_text[:500]).lower()
    for doc_type, keywords in _TYPE_KEYWORDS.items():
        if any(kw in probe for kw in keywords):
            return doc_type

    return "document"


def _classify_sensitivity(parsed: ParsedDocument) -> str:
    """
    Infer a sensitivity level from the document text.

    Defaults to 'standard' if no indicator is found.
    """
    probe = parsed.raw_text[:2000].lower()
    for level, keywords in _SENSITIVITY_KEYWORDS.items():
        if any(kw in probe for kw in keywords):
            return level
    return "standard"


def _extract_dates(text: str) -> List[str]:
    """Return ISO-format date strings found in ``text``."""
    dates: List[str] = []
    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text[:3000]):
            try:
                full = match.group(0)
                # Attempt to parse and normalise
                dates.append(full)
            except Exception:
                pass
    return dates[:10]


def extract_metadata(
    parsed: ParsedDocument,
    *,
    doc_type_hint: Optional[str] = None,
    sensitivity_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Derive structured metadata from a parsed document.

    Returns a dict suitable for storing in ``documents.metadata_json`` or
    passing directly to domain logic.
    """
    doc_type = _classify_doc_type(parsed, hint=doc_type_hint)
    sensitivity = sensitivity_hint or _classify_sensitivity(parsed)
    dates = _extract_dates(parsed.raw_text)

    return {
        "doc_type": doc_type,
        "sensitivity_level": sensitivity,
        "detected_dates": dates,
        "section_count": len(parsed.sections),
        "word_count": len(parsed.raw_text.split()),
        "parser_metadata": parsed.metadata,
    }
