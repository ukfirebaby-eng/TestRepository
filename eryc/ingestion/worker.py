"""
Ingest worker for the ERYC Document Intelligence Console.

Phase B-1: Accept queued ingest jobs, copy source files to the local spool,
parse, chunk, extract metadata, persist document versions and update indexes.

A single worker instance is preferred to avoid SQLite write-lock contention
(spec §3.2, §11.1).
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from eryc.config import Settings, get_settings
from eryc.database.connection import open_connection
from eryc.ingestion.chunker import Chunker
from eryc.ingestion.indexer import Indexer
from eryc.ingestion.metadata import extract_metadata
from eryc.ingestion.parsers.base import get_parser

logger = logging.getLogger(__name__)


class IngestWorker:
    """
    Background worker that polls the ``ingest_jobs`` table and processes
    each queued job in order.

    Serialises write-heavy operations to avoid lock contention.
    Implements the pipeline described in spec §9.1.
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._chunker = Chunker(max_chunk_tokens=400)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background polling loop. Idempotent."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="ingest-worker",
            daemon=True,
        )
        self._thread.start()
        logger.info("Ingest worker started")

    def stop(self, wait: bool = True) -> None:
        """Signal the worker to stop after its current job."""
        self._stop_event.set()
        if wait and self._thread is not None:
            self._thread.join(timeout=30)
        logger.info("Ingest worker stopped")

    # ------------------------------------------------------------------
    # Queue API — called by the API layer
    # ------------------------------------------------------------------

    def enqueue(
        self,
        conn: sqlite3.Connection,
        *,
        workspace_id: str,
        source_path: str,
        collection_id: Optional[str] = None,
        doc_type: Optional[str] = None,
        sensitivity_level: str = "standard",
    ) -> str:
        """
        Insert a new ingest job into the queue.

        Returns the ``job_id`` of the created job.
        """
        job_id = "job_" + uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO ingest_jobs(
                job_id, workspace_id, collection_id, source_path,
                doc_type, sensitivity_level, status, queued_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'queued', ?)
            """,
            (
                job_id,
                workspace_id,
                collection_id,
                source_path,
                doc_type,
                sensitivity_level,
                now,
            ),
        )
        conn.commit()
        logger.info("Queued ingest job %s for %s", job_id, source_path)
        return job_id

    # ------------------------------------------------------------------
    # Internal polling loop
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                conn = open_connection(self._settings.db_path, settings=self._settings)
                self._process_next_job(conn)
            except Exception as exc:
                logger.exception("Error in ingest poll loop: %s", exc)
            self._stop_event.wait(timeout=self._settings.ingest_worker_poll_interval)

    def _process_next_job(self, conn: sqlite3.Connection) -> None:
        """Pick the oldest queued job and process it."""
        row = conn.execute(
            """
            SELECT job_id, workspace_id, collection_id, source_path,
                   doc_type, sensitivity_level
            FROM ingest_jobs
            WHERE status = 'queued'
            ORDER BY queued_at ASC
            LIMIT 1
            """
        ).fetchone()

        if row is None:
            return

        job_id = row["job_id"]
        logger.info("Processing ingest job %s", job_id)
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE ingest_jobs SET status='running', started_at=? WHERE job_id=?",
            (now, job_id),
        )
        conn.commit()

        try:
            document_id = self._run_ingest(conn, dict(row))
            conn.execute(
                """
                UPDATE ingest_jobs
                SET status='completed', completed_at=?, document_id=?
                WHERE job_id=?
                """,
                (datetime.now(timezone.utc).isoformat(), document_id, job_id),
            )
            conn.commit()
            logger.info("Ingest job %s completed → document %s", job_id, document_id)
        except Exception as exc:
            logger.exception("Ingest job %s failed: %s", job_id, exc)
            conn.execute(
                "UPDATE ingest_jobs SET status='failed', error_message=? WHERE job_id=?",
                (str(exc), job_id),
            )
            conn.commit()

    def _run_ingest(self, conn: sqlite3.Connection, job: dict) -> str:
        """
        Execute the full ingestion pipeline for a single job.

        Follows the steps in spec §9.1:
          1. Copy/stream source file to local spool
          2. Parse into canonical text
          3. Extract metadata
          4. Chunk
          5. Persist document and version
          6. Index (FTS5 + optional vector)

        Returns the ``document_id`` of the created or updated document.
        """
        source_path = Path(job["source_path"])
        if not source_path.is_absolute():
            source_path = source_path.resolve()

        # Step 1: Copy to local spool.
        spool_path = self._copy_to_spool(source_path)

        # Step 2: Parse.
        parser = get_parser(spool_path)
        parsed = parser.parse(spool_path, doc_type=job.get("doc_type"))

        # Step 3: Metadata.
        meta = extract_metadata(
            parsed,
            doc_type_hint=job.get("doc_type"),
            sensitivity_hint=job.get("sensitivity_level"),
        )

        # Step 4–6: Persist and index.
        document_id = self._persist_and_index(
            conn,
            parsed=parsed,
            meta=meta,
            job=job,
        )

        return document_id

    def _copy_to_spool(self, source: Path) -> Path:
        """Copy the source file to the local spool directory."""
        spool_dir = self._settings.spool_dir
        spool_dir.mkdir(parents=True, exist_ok=True)
        dest = spool_dir / source.name
        try:
            shutil.copy2(str(source), str(dest))
        except (shutil.SameFileError, OSError):
            dest = source  # Use in-place if copy fails (e.g., already local)
        return dest

    def _persist_and_index(
        self,
        conn: sqlite3.Connection,
        *,
        parsed,
        meta: dict,
        job: dict,
    ) -> str:
        """Create or update the document, version and chunk records."""
        now = datetime.now(timezone.utc).isoformat()

        # Check for existing document with the same source path.
        existing = conn.execute(
            "SELECT document_id, current_version_id FROM documents WHERE source_path=? AND workspace_id=?",
            (parsed.source_path, job["workspace_id"]),
        ).fetchone()

        if existing:
            document_id = existing["document_id"]
            # Determine next version number.
            max_ver = conn.execute(
                "SELECT MAX(version_number) FROM document_versions WHERE document_id=?",
                (document_id,),
            ).fetchone()[0] or 0
            version_number = max_ver + 1
        else:
            document_id = "doc_" + uuid.uuid4().hex
            version_number = 1
            conn.execute(
                """
                INSERT INTO documents(
                    document_id, workspace_id, collection_id, doc_type,
                    canonical_title, source_path, sensitivity_level,
                    access_scope, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'workspace', ?, ?)
                """,
                (
                    document_id,
                    job["workspace_id"],
                    job.get("collection_id"),
                    meta["doc_type"],
                    parsed.canonical_title,
                    parsed.source_path,
                    meta["sensitivity_level"],
                    now,
                    now,
                ),
            )

        # Create the version record.
        version_id = "ver_" + uuid.uuid4().hex
        conn.execute(
            """
            INSERT INTO document_versions(
                version_id, document_id, version_number, content_hash,
                parsed_at, index_status, created_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (version_id, document_id, version_number, parsed.content_hash, now, now),
        )

        # Update the document's current version pointer.
        conn.execute(
            "UPDATE documents SET current_version_id=?, updated_at=? WHERE document_id=?",
            (version_id, now, document_id),
        )
        conn.commit()

        # Chunk the document.
        chunks = self._chunker.chunk_document(
            parsed, version_id=version_id, document_id=document_id
        )

        # Index.
        indexer = Indexer(conn, self._settings)
        indexer.index_chunks(chunks)
        indexer.mark_version_indexed(version_id)

        return document_id
