from pathlib import Path
from typing import Dict, List

_ENV_KEYS: List[str] = [
    "VAULT_PATH",
    "LLM_PROVIDER",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "FAST_MODEL",
    "SMART_MODEL",
    "DIAMOND_MINER_CLAIM_LAYER",
]


def read_env(path: Path) -> Dict[str, str]:
    """Parse KEY=VALUE lines from a .env file. Returns dict of present keys only."""
    result: Dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key, _, val = stripped.partition("=")
            result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def write_env(path: Path, values: Dict[str, str]) -> None:
    """Write managed KEY=VALUE lines, preserving comments and unrecognised keys."""
    existing_lines: List[str] = []
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8").splitlines()

    preserved: List[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            preserved.append(line)
            continue
        if "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key not in _ENV_KEYS:
                preserved.append(line)

    out_lines = preserved[:]
    for key in _ENV_KEYS:
        val = values.get(key, "")
        if val:
            out_lines.append(f'{key}="{val}"')
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def mask_key(value: str) -> str:
    """Return first 12 chars + '…' for values longer than 12 characters."""
    if len(value) > 12:
        return value[:12] + "\u2026"
    return value
