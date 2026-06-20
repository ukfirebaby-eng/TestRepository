import os
from collections.abc import Mapping
from enum import StrEnum


class PipelineMode(StrEnum):
    LEGACY = "legacy"
    SHADOW = "shadow"
    CLAIMS = "claims"


def resolve_pipeline_mode(env: Mapping[str, str] | None = None) -> PipelineMode:
    values = os.environ if env is None else env
    explicit = values.get("DIAMOND_MINER_PIPELINE_MODE", "").strip().lower()
    if explicit:
        return PipelineMode(explicit)

    claim_layer = values.get("DIAMOND_MINER_CLAIM_LAYER", "").strip() == "1"
    claim_promotion = values.get("DIAMOND_MINER_USE_CLAIM_PROMOTION", "").strip() == "1"
    if claim_layer and claim_promotion:
        return PipelineMode.CLAIMS
    if claim_layer:
        return PipelineMode.SHADOW
    return PipelineMode.LEGACY
