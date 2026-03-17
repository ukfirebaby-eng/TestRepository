"""Storage backends: document store, object store."""

from .document_store import InMemoryDocumentStore
from .index_store import InMemoryIndexStore
from .object_store import LocalObjectStore

__all__ = ["InMemoryDocumentStore", "InMemoryIndexStore", "LocalObjectStore"]
