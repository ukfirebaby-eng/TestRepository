"""LangSmith run logging bridge.

No-op when LANGSMITH_API_KEY is not set.
LangGraph natively supports LangSmith tracing when the env var is present.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def configure_langsmith(api_key: str = "") -> bool:
    """Configure LangSmith tracing if API key is available.

    Returns True if LangSmith was successfully configured.
    """
    key = api_key or os.environ.get("LANGSMITH_API_KEY", "")
    if not key:
        logger.debug("LANGSMITH_API_KEY not set; LangSmith tracing disabled")
        return False

    try:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = key
        os.environ.setdefault("LANGCHAIN_PROJECT", "rag-system")
        logger.info("LangSmith tracing enabled (project=%s)", os.environ["LANGCHAIN_PROJECT"])
        return True
    except Exception as e:
        logger.warning("Failed to configure LangSmith: %s", e)
        return False
