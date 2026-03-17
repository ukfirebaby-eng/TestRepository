"""Base parser interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedSection:
    title: str
    text: str
    breadcrumbs: list[str] = field(default_factory=list)
    level: int = 1  # heading level (1 = top)


@dataclass
class ParsedDocument:
    title: str
    sections: list[ParsedSection]
    metadata: dict = field(default_factory=dict)
    raw_text: str = ""


class BaseParser(ABC):
    @abstractmethod
    def parse(self, content: bytes, source_uri: str = "") -> ParsedDocument:
        """Parse raw bytes into a structured document."""
