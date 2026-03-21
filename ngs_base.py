"""
ngs_base.py — Novel Genesis System: Base classes and configuration.

Provides:
  - NGSConfig     : runtime configuration dataclass
  - NGSLogger     : structured logger (terminal + ngs_run.jsonl)
  - NGSBaseTool   : abstract base class for all pipeline nodes
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class NGSConfig:
    """Runtime configuration for the Novel Genesis pipeline.

    All fields have sensible defaults so the pipeline is usable out of the
    box.  Override by passing keyword arguments or loading from ngs_config.toml.
    """
    output_dir: str = "novel_output"
    beta_interval: int = 10          # every Nth scene gets a beta report
    structural_model: str = "claude-sonnet-4-6"
    prose_model: str = "claude-sonnet-4-6"
    max_revision_passes: int = 3

    # --- Phase J.2 ---
    overload_threshold: float = 0.60  # probability threshold for overload alert


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

_LEVEL_SYMBOLS = {
    "info": " ",
    "warn": "!",
    "err":  "✗",
    "ok":   "✓",
}


class NGSLogger:
    """Structured logger that writes to stdout *and* appends JSON lines to
    ``ngs_run.jsonl`` inside the configured output directory.

    Level rendering:
        info →   [HH:MM:SS] message
        warn → ! [HH:MM:SS] message
        err  → ✗ [HH:MM:SS] message
        ok   → ✓ [HH:MM:SS] message
    """

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._jsonl_path = output_dir / "ngs_run.jsonl"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Python stdlib logger for any downstream integrations
        self._logger = logging.getLogger("ngs")
        if not self._logger.handlers:
            self._logger.addHandler(logging.NullHandler())
        self._logger.setLevel(logging.DEBUG)

    def log(
        self,
        message: str,
        level: str = "info",
        node: Optional[str] = None,
    ) -> None:
        """Emit *message* at *level* ('info', 'warn', 'err', 'ok').

        Always writes to stdout and appends a JSON record to ngs_run.jsonl.
        """
        now = datetime.now(tz=timezone.utc)
        ts = now.strftime("%H:%M:%S")
        symbol = _LEVEL_SYMBOLS.get(level, " ")
        prefix = f"{symbol} [{ts}]"
        node_tag = f" ({node})" if node else ""
        print(f"{prefix}{node_tag} {message}", file=sys.stdout, flush=True)

        record: dict[str, Any] = {
            "ts": now.isoformat(),
            "level": level,
            "message": message,
        }
        if node:
            record["node"] = node
        try:
            with self._jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except OSError:
            pass  # never crash the pipeline over a logging failure


# ---------------------------------------------------------------------------
# Base tool
# ---------------------------------------------------------------------------

class NGSBaseTool:
    """Abstract base class for all Novel Genesis pipeline nodes.

    Subclasses receive a shared ``NGSConfig`` and ``NGSLogger``, plus
    convenience helpers ``_log``, ``_save``, and ``_call_agent``.
    """

    def __init__(self, config: NGSConfig) -> None:
        self.config = config
        self.output_dir = Path(config.output_dir)
        self._logger = NGSLogger(self.output_dir)

        # Agent handles (populated by the concrete pipeline subclass)
        self.structural_llm: Any = None
        self.prose_llm: Any = None
        self.prompts: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def _log(
        self,
        message: str,
        level: str = "info",
        node: Optional[str] = None,
    ) -> None:
        """Delegate to the NGSLogger instance."""
        self._logger.log(message, level=level, node=node)

    def _save(self, relative_path: str, content: str) -> Path:
        """Write *content* to ``output_dir / relative_path``, creating
        intermediate directories as needed.  Returns the resolved Path.
        """
        target = self.output_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def _call_agent(
        self,
        agent: Any,
        system_prompt: str,
        user_message: str,
        label: str = "",
    ) -> str:
        """Invoke *agent* with the given prompts and return the text response.

        In the stub implementation this raises ``NotImplementedError``; the
        real pipeline wires in an Anthropic SDK client here.
        """
        raise NotImplementedError(
            "_call_agent must be overridden by a concrete pipeline subclass."
        )
