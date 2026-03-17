"""Object store for raw documents and parsed artifacts.

Dev mode: local filesystem under a configurable base directory.
Production: swap for an S3-compatible client.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class LocalObjectStore:
    """Store raw document artifacts on the local filesystem."""

    def __init__(self, base_path: str = "./rag_objects") -> None:
        self.base = Path(base_path)
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, tenant_id: str, doc_id: str, artifact: str) -> Path:
        tenant_dir = self.base / tenant_id
        tenant_dir.mkdir(exist_ok=True)
        return tenant_dir / f"{doc_id}.{artifact}"

    def put(self, tenant_id: str, doc_id: str, artifact: str, data: bytes) -> str:
        """Store bytes. Returns the storage key."""
        path = self._path(tenant_id, doc_id, artifact)
        path.write_bytes(data)
        return str(path)

    def put_json(self, tenant_id: str, doc_id: str, artifact: str, obj: Any) -> str:
        return self.put(tenant_id, doc_id, artifact, json.dumps(obj).encode())

    def get(self, tenant_id: str, doc_id: str, artifact: str) -> bytes | None:
        path = self._path(tenant_id, doc_id, artifact)
        return path.read_bytes() if path.exists() else None

    def get_json(self, tenant_id: str, doc_id: str, artifact: str) -> Any | None:
        raw = self.get(tenant_id, doc_id, artifact)
        return json.loads(raw) if raw else None

    def delete(self, tenant_id: str, doc_id: str) -> int:
        """Delete all artifacts for a document. Returns count deleted."""
        tenant_dir = self.base / tenant_id
        if not tenant_dir.exists():
            return 0
        deleted = 0
        for f in tenant_dir.glob(f"{doc_id}.*"):
            f.unlink()
            deleted += 1
        return deleted

    def exists(self, tenant_id: str, doc_id: str, artifact: str) -> bool:
        return self._path(tenant_id, doc_id, artifact).exists()
