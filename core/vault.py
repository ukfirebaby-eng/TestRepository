import os
import json
import sqlite3
import threading
import chromadb
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Any, Optional

from core.accuracy.schemas import CanonicalEntity, DocumentManifest, EvidenceSpan, ExtractionFailure, ExtractedClaim, ValidationResult


class HybridVault:
    def __init__(self, tenant_id: str, base_dir: str = "./vaults"):
        """
        Initializes physical file isolation for the given tenant and
        establishes connections to both SQLite and ChromaDB.
        """
        self.tenant_id = tenant_id
        self.vault_path = os.path.join(base_dir, tenant_id)

        # Ensure the isolated tenant directory exists
        os.makedirs(self.vault_path, exist_ok=True)

        # 1. Initialize SQLite (The Graph Topology Engine)
        self.sqlite_path = os.path.join(self.vault_path, "graph.sqlite")
        self.conn = sqlite3.connect(self.sqlite_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Returns dict-like rows instead of tuples

        # Threading lock — serialises all SQLite writes during parallel ingestion
        self._write_lock = threading.Lock()

        # 2. Initialize ChromaDB (The Semantic Vector Engine)
        self.chroma_client = chromadb.PersistentClient(path=os.path.join(self.vault_path, "chroma"))
        self.collection = self.chroma_client.get_or_create_collection(
            name="document_chunks",
            metadata={"hnsw:space": "cosine"}  # Optimize for semantic similarity
        )

        # Lock in the schemas immediately
        self.initialize_schemas()

    def initialize_schemas(self) -> None:
        """Executes the SQLite CREATE TABLE statements if they do not exist."""
        cursor = self.conn.cursor()

        # Nodes Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                name TEXT NOT NULL
            )
        """)

        # Edges Table with the critical source_chunk_id bridge
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL DEFAULT '',
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relationship TEXT NOT NULL,
                source_chunk_id TEXT NOT NULL,
                claim_id TEXT,
                evidence_span_ids TEXT,
                FOREIGN KEY(source_id) REFERENCES nodes(id),
                FOREIGN KEY(target_id) REFERENCES nodes(id)
            )
        """)

        # Traversal Indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_relationship ON edges(relationship)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_document ON edges(document_id)")
        for col in ["claim_id", "evidence_span_ids"]:
            try:
                cursor.execute(f"ALTER TABLE edges ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass

        # Documents Table — tracks every ingested document for UI restore
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_manifests (
                document_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                parser_version TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                llm_model TEXT NOT NULL,
                document_anchor_date TEXT,
                validation_status TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evidence_spans (
                span_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                chunk_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                section_title TEXT NOT NULL DEFAULT '',
                text TEXT NOT NULL,
                span_type TEXT NOT NULL,
                bbox_json TEXT,
                source_hash TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evidence_spans_document ON evidence_spans(document_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_evidence_spans_chunk ON evidence_spans(chunk_id)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extracted_claims (
                claim_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                claim_type TEXT NOT NULL,
                subject TEXT NOT NULL,
                predicate TEXT NOT NULL,
                object TEXT NOT NULL,
                modality TEXT NOT NULL,
                certainty TEXT NOT NULL,
                status TEXT NOT NULL,
                date_start TEXT,
                date_end TEXT,
                owner TEXT NOT NULL DEFAULT '',
                evidence_span_ids TEXT NOT NULL,
                source_quote TEXT NOT NULL,
                confidence REAL NOT NULL,
                validation_status TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_extracted_claims_document ON extracted_claims(document_id)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS claim_validation_results (
                claim_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                status TEXT NOT NULL,
                reasons_json TEXT NOT NULL,
                can_promote INTEGER NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_claim_validation_document ON claim_validation_results(document_id)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS canonical_entities (
                entity_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                canonical_name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                aliases_json TEXT NOT NULL,
                source_span_ids_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                human_locked INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (document_id, entity_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_canonical_entities_document ON canonical_entities(document_id)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extraction_failures (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                span_id TEXT NOT NULL,
                agent TEXT NOT NULL,
                error TEXT NOT NULL,
                raw_payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accuracy_review_decisions (
                document_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL,
                state TEXT NOT NULL,
                kind TEXT NOT NULL,
                label TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (document_id, candidate_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_extraction_failures_document ON extraction_failures(document_id)")

        # Friction Lines Table — persists computed diamonds so they survive restarts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS friction_lines (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                diamond TEXT NOT NULL,
                provenance_ids TEXT NOT NULL
            )
        """)

        # Friction Lines Index
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_friction_lines_document ON friction_lines(document_id)")

        # Fragility Lines Table — persists DLI hub node analysis
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fragility_lines (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                hub_node_id TEXT NOT NULL,
                dependency_count INTEGER NOT NULL DEFAULT 0,
                insight TEXT NOT NULL,
                cascade_nodes TEXT NOT NULL
            )
        """)

        # Fragility Lines Index
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fragility_lines_document ON fragility_lines(document_id)")

        # Chronological Friction Lines Table — persists time-conflict diamonds
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chronological_friction_lines (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                diamond TEXT NOT NULL,
                provenance_ids TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chron_friction_document ON chronological_friction_lines(document_id)")

        # Phase 2: add severity/probability scoring columns to friction tables
        for col, table in [
            ("severity",    "friction_lines"),
            ("probability", "friction_lines"),
            ("severity",    "chronological_friction_lines"),
            ("probability", "chronological_friction_lines"),
        ]:
            assert table in {"friction_lines", "chronological_friction_lines"}
            assert col in {"severity", "probability"}
            try:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN {col} INTEGER DEFAULT 3"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists on subsequent starts

        # Structured finding metadata lets the UI explain evidence without
        # reverse-engineering meaning from graph endpoints.
        for table in ["friction_lines", "chronological_friction_lines"]:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN finding_json TEXT")
            except sqlite3.OperationalError:
                pass

        # Temporal Metadata Table — stores ISO 8601 dates per node
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS temporal_metadata (
                node_id TEXT PRIMARY KEY,
                start_date TEXT,
                end_date TEXT,
                duration_days INTEGER,
                is_milestone BOOLEAN
            )
        """)

        # Executive Summaries Cache — persists AI-generated plain-English reports
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS executive_summaries (
                document_id   TEXT PRIMARY KEY,
                generated_at  TEXT NOT NULL,
                model         TEXT NOT NULL,
                report_json   TEXT NOT NULL
            )
        """)

        # Narrative Reports Cache — persists full narrative analysis reports
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS narrative_reports (
                document_id  TEXT PRIMARY KEY,
                generated_at TEXT NOT NULL,
                model        TEXT NOT NULL,
                report_json  TEXT NOT NULL
            )
        """)

        # Risk Simulations Cache — persists Monte Carlo / risk simulation results
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS risk_simulations (
                document_id  TEXT PRIMARY KEY,
                generated_at TEXT NOT NULL,
                result_json  TEXT NOT NULL
            )
        """)

        self.conn.commit()

    def save_document_manifest(self, manifest: DocumentManifest) -> None:
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO document_manifests
                (document_id, filename, mime_type, source_hash, ingested_at, parser_version,
                 schema_version, embedding_model, llm_model, document_anchor_date, validation_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                manifest.document_id,
                manifest.filename,
                manifest.mime_type,
                manifest.source_hash,
                manifest.ingested_at.isoformat(),
                manifest.parser_version,
                manifest.schema_version,
                manifest.embedding_model,
                manifest.llm_model,
                manifest.document_anchor_date.isoformat() if manifest.document_anchor_date else None,
                manifest.validation_status,
            ))
            self.conn.commit()

    def get_document_manifest(self, document_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM document_manifests WHERE document_id = ?", (document_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def insert_evidence_spans(self, spans: List[EvidenceSpan]) -> None:
        if not spans:
            return
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO evidence_spans
                (span_id, document_id, chunk_id, page_number, section_title, text, span_type, bbox_json, source_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    span.span_id,
                    span.document_id,
                    span.chunk_id,
                    span.page_number,
                    span.section_title,
                    span.text,
                    span.span_type,
                    span.bbox.model_dump_json() if span.bbox else None,
                    span.source_hash,
                )
                for span in spans
            ])
            self.conn.commit()

    def list_evidence_spans(self, document_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM evidence_spans WHERE document_id = ? ORDER BY span_id", (document_id,))
        return [dict(row) for row in cursor.fetchall()]

    def insert_extracted_claims(self, claims: List[ExtractedClaim]) -> None:
        if not claims:
            return
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO extracted_claims
                (claim_id, document_id, claim_type, subject, predicate, object, modality, certainty,
                 status, date_start, date_end, owner, evidence_span_ids, source_quote, confidence, validation_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    claim.claim_id,
                    claim.document_id,
                    claim.claim_type,
                    claim.subject,
                    claim.predicate,
                    claim.object,
                    claim.modality,
                    claim.certainty,
                    claim.status,
                    claim.date_start.isoformat() if claim.date_start else None,
                    claim.date_end.isoformat() if claim.date_end else None,
                    claim.owner,
                    json.dumps(claim.evidence_span_ids),
                    claim.source_quote,
                    claim.confidence,
                    claim.validation_status,
                )
                for claim in claims
            ])
            self.conn.commit()

    def list_extracted_claims(self, document_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM extracted_claims WHERE document_id = ? ORDER BY claim_id", (document_id,))
        rows = []
        for row in cursor.fetchall():
            item = dict(row)
            item["evidence_span_ids"] = json.loads(item["evidence_span_ids"])
            rows.append(item)
        return rows

    def insert_validation_results(self, results: List[ValidationResult]) -> None:
        if not results:
            return
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO claim_validation_results
                (claim_id, document_id, status, reasons_json, can_promote)
                VALUES (?, ?, ?, ?, ?)
            """, [
                (
                    result.claim_id,
                    result.document_id,
                    result.status,
                    json.dumps(result.reasons),
                    1 if result.can_promote else 0,
                )
                for result in results
            ])
            self.conn.commit()

    def list_validation_results(self, document_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM claim_validation_results WHERE document_id = ? ORDER BY claim_id",
            (document_id,),
        )
        rows = []
        for row in cursor.fetchall():
            item = dict(row)
            item["reasons"] = json.loads(item.pop("reasons_json"))
            rows.append(item)
        return rows

    def insert_canonical_entities(self, document_id: str, entities: List[CanonicalEntity]) -> None:
        if not entities:
            return
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO canonical_entities
                (entity_id, document_id, canonical_name, entity_type, aliases_json,
                 source_span_ids_json, confidence, human_locked)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    entity.entity_id,
                    document_id,
                    entity.canonical_name,
                    entity.entity_type,
                    json.dumps(entity.aliases),
                    json.dumps(entity.source_span_ids),
                    entity.confidence,
                    1 if entity.human_locked else 0,
                )
                for entity in entities
            ])
            self.conn.commit()

    def list_canonical_entities(self, document_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM canonical_entities WHERE document_id = ? ORDER BY entity_id",
            (document_id,),
        )
        rows = []
        for row in cursor.fetchall():
            item = dict(row)
            item["aliases"] = json.loads(item.pop("aliases_json"))
            item["source_span_ids"] = json.loads(item.pop("source_span_ids_json"))
            rows.append(item)
        return rows

    def list_extraction_failures(self, document_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM extraction_failures WHERE document_id = ? ORDER BY created_at, id",
            (document_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def save_accuracy_review_decision(
        self,
        *,
        document_id: str,
        candidate_id: str,
        state: str,
        kind: str,
        label: str,
    ) -> Dict[str, Any]:
        """Upserts a human review decision for an accuracy graph mismatch candidate."""
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO accuracy_review_decisions
                   (document_id, candidate_id, state, kind, label, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (document_id, candidate_id, state, kind, label, updated_at),
            )
            self.conn.commit()
        return {
            "document_id": document_id,
            "candidate_id": candidate_id,
            "state": state,
            "kind": kind,
            "label": label,
            "updated_at": updated_at,
        }

    def list_accuracy_review_decisions(self, document_id: str) -> Dict[str, Dict[str, Any]]:
        """Returns review decisions keyed by candidate ID for quick frontend hydration."""
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT document_id, candidate_id, state, kind, label, updated_at
               FROM accuracy_review_decisions
               WHERE document_id = ?
               ORDER BY updated_at DESC""",
            (document_id,),
        )
        return {
            row["candidate_id"]: {
                "document_id": row["document_id"],
                "candidate_id": row["candidate_id"],
                "state": row["state"],
                "kind": row["kind"],
                "label": row["label"],
                "updated_at": row["updated_at"],
            }
            for row in cursor.fetchall()
        }

    def insert_extraction_failures(self, failures: List[ExtractionFailure]) -> None:
        if not failures:
            return
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO extraction_failures
                (id, document_id, span_id, agent, error, raw_payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    failure.id,
                    failure.document_id,
                    failure.span_id,
                    failure.agent,
                    failure.error,
                    failure.raw_payload,
                    failure.created_at.isoformat(),
                )
                for failure in failures
            ])
            self.conn.commit()

    def insert_document_chunk(self, chunk_id: str, document_id: str, text: str, page: int, bbox: Tuple[float, float, float, float]) -> None:
        """
        Embeds the text and stores it in ChromaDB along with the strict
        geometric metadata dictionary.
        """
        bbox_meta = {"x0": bbox[0], "y0": bbox[1], "x1": bbox[2], "y1": bbox[3]} if bbox else {"x0": 0.0, "y0": 0.0, "x1": 0.0, "y1": 0.0}
        self.collection.add(
            ids=[chunk_id],
            documents=[text],
            metadatas=[{"document_id": document_id, "page_number": page, **bbox_meta}]
        )

    def insert_graph_topology(self, nodes: List[Dict[str, str]], edges: List[Dict[str, str]], source_chunk_id: str, document_id: str = "") -> None:
        """
        Takes the JSON output from the Deconstructor Agent and safely inserts
        it into SQLite. Wraps the insertion in a transaction to prevent partial writes.
        """
        with self._write_lock:
            cursor = self.conn.cursor()
            try:
                # Insert Nodes (IGNORE if they already exist from a previous chunk)
                for node in nodes:
                    cursor.execute("""
                        INSERT OR IGNORE INTO nodes (id, label, name)
                        VALUES (?, ?, ?)
                    """, (node['id'], node['label'], node['name']))

                # Insert Edges (Attach the ChromaDB bridge ID and document scope to every one)
                for edge in edges:
                    # Scope the edge ID to this document so re-ingesting doesn't collide
                    edge_id = f"{document_id}_{edge['source_id']}_{edge['relationship']}_{edge['target_id']}"
                    cursor.execute("""
                        INSERT OR IGNORE INTO edges
                        (id, document_id, source_id, target_id, relationship, source_chunk_id, claim_id, evidence_span_ids)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        edge_id,
                        document_id,
                        edge['source_id'],
                        edge['target_id'],
                        edge['relationship'],
                        source_chunk_id,
                        edge.get("claim_id"),
                        json.dumps(edge.get("evidence_span_ids")) if edge.get("evidence_span_ids") else None,
                    ))

                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                print(f"[!] Graph Insertion Failed for chunk {source_chunk_id}: {e}")
                raise

    def get_triangular_conflicts(self, document_id: str = "") -> List[Dict[str, Any]]:
        """
        The zero-cost structural tension query. Finds A -> REQUIRES -> B, but C -> BLOCKS -> B.
        Scoped to a single document when document_id is provided.
        """
        cursor = self.conn.cursor()
        if document_id:
            query = """
                SELECT
                    e1.source_id AS node_a,
                    e1.target_id AS node_b,
                    e2.source_id AS node_c,
                    e1.source_chunk_id AS chunk_requires,
                    e2.source_chunk_id AS chunk_blocks,
                    e1.claim_id AS claim_requires,
                    e2.claim_id AS claim_blocks,
                    e1.evidence_span_ids AS evidence_requires,
                    e2.evidence_span_ids AS evidence_blocks
                FROM edges e1
                JOIN edges e2 ON e1.target_id = e2.target_id
                WHERE e1.relationship = 'REQUIRES'
                  AND e2.relationship = 'BLOCKS'
                  AND e1.document_id = ?
                  AND e2.document_id = ?
            """
            cursor.execute(query, (document_id, document_id))
        else:
            query = """
                SELECT
                    e1.source_id AS node_a,
                    e1.target_id AS node_b,
                    e2.source_id AS node_c,
                    e1.source_chunk_id AS chunk_requires,
                    e2.source_chunk_id AS chunk_blocks,
                    e1.claim_id AS claim_requires,
                    e2.claim_id AS claim_blocks,
                    e1.evidence_span_ids AS evidence_requires,
                    e2.evidence_span_ids AS evidence_blocks
                FROM edges e1
                JOIN edges e2 ON e1.target_id = e2.target_id
                WHERE e1.relationship = 'REQUIRES'
                  AND e2.relationship = 'BLOCKS'
            """
            cursor.execute(query)

        conflicts = []
        for row in cursor.fetchall():
            item = dict(row)
            item["claim_ids"] = [
                claim_id
                for claim_id in [item.pop("claim_requires", None), item.pop("claim_blocks", None)]
                if claim_id
            ]
            evidence_span_ids: List[str] = []
            for key in ["evidence_requires", "evidence_blocks"]:
                raw = item.pop(key, None)
                if not raw:
                    continue
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        evidence_span_ids.extend(str(span_id) for span_id in parsed if span_id)
                    else:
                        evidence_span_ids.append(str(parsed))
                except (json.JSONDecodeError, TypeError):
                    evidence_span_ids.append(str(raw))
            item["evidence_span_ids"] = list(dict.fromkeys(evidence_span_ids))
            conflicts.append(item)
        return conflicts

    def get_chunk_provenance(self, chunk_id: str) -> Dict[str, Any]:
        """
        Retrieves the exact geometric metadata and text from ChromaDB.
        """
        result = self.collection.get(
            ids=[chunk_id],
            include=["documents", "metadatas"]
        )

        if not result['ids']:
            return {}

        return {
            "chunk_id": chunk_id,
            "text": result['documents'][0],
            "geometry": result['metadatas'][0]
        }

    def get_node_names(self, node_ids: List[str]) -> Dict[str, str]:
        """Returns a mapping of node_id -> human-readable name for a list of IDs."""
        if not node_ids:
            return {}
        cursor = self.conn.cursor()
        placeholders = ','.join('?' * len(node_ids))
        cursor.execute(f"SELECT id, name FROM nodes WHERE id IN ({placeholders})", node_ids)
        return {row['id']: row['name'] for row in cursor.fetchall()}

    def insert_document(self, document_id: str, name: str) -> None:
        """Records a document ingestion so it can be listed and restored after a restart."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO documents (id, name, created_at)
            VALUES (?, ?, ?)
        """, (document_id, name, datetime.now(timezone.utc).isoformat()))
        self.conn.commit()

    def list_documents(self) -> List[Dict[str, Any]]:
        """Returns all ingested documents ordered by most recent first."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, created_at FROM documents ORDER BY created_at DESC")
        return [dict(row) for row in cursor.fetchall()]

    def upsert_friction_lines(self, document_id: str, friction_lines: List[Dict[str, Any]]) -> None:
        """Persists the computed friction lines to SQLite so they survive restarts."""
        cursor = self.conn.cursor()
        # Clear old results for this document before writing fresh ones
        cursor.execute("DELETE FROM friction_lines WHERE document_id = ?", (document_id,))
        for i, fl in enumerate(friction_lines):
            cursor.execute("""
                INSERT INTO friction_lines
                (id, document_id, source_node_id, target_node_id, diamond, provenance_ids, severity, probability, finding_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"{document_id}_fl_{i}",
                document_id,
                fl["source"],
                fl["target"],
                fl["diamond"],
                json.dumps(fl["provenance_ids"]),
                fl.get("severity", 3),
                fl.get("probability", 3),
                json.dumps(fl["finding"]) if fl.get("finding") else None,
            ))
        self.conn.commit()

    def clear_all(self) -> None:
        """Wipes every table and the ChromaDB collection. Irreversible."""
        tables = [
            "friction_lines",
            "fragility_lines",
            "chronological_friction_lines",
            "temporal_metadata",
            "edges",
            "nodes",
            "executive_summaries",
            "narrative_reports",
            "risk_simulations",
            "accuracy_review_decisions",
            "extraction_failures",
            "canonical_entities",
            "claim_validation_results",
            "extracted_claims",
            "evidence_spans",
            "document_manifests",
            "documents",
        ]
        with self.conn:
            cursor = self.conn.cursor()
            for table in tables:
                cursor.execute(f"DELETE FROM {table}")  # noqa: S608 — table names are hardcoded

        try:
            existing = self.collection.get()
            if existing["ids"]:
                self.collection.delete(ids=existing["ids"])
        except Exception as e:
            print(f"[!] Vault: ChromaDB clear_all failed: {e}")
            raise

    def delete_document(self, document_id: str) -> None:
        """
        Permanently removes a document and all its associated data.
        SQLite is committed first; ChromaDB is cleaned up afterwards.
        If ChromaDB fails, the SQLite deletion has already committed — the document
        is gone from all UI queries and the orphaned chunks are unreachable.
        """
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM friction_lines WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM fragility_lines WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM chronological_friction_lines WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM accuracy_review_decisions WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM extraction_failures WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM canonical_entities WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM claim_validation_results WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM extracted_claims WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM evidence_spans WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM document_manifests WHERE document_id = ?", (document_id,))
            # Note: deletes temporal data for ALL nodes appearing in this document's edges.
            # If a node is shared across documents, its temporal data will be wiped.
            cursor.execute("""
                DELETE FROM temporal_metadata
                WHERE node_id IN (
                    SELECT source_id FROM edges WHERE document_id = ?
                    UNION
                    SELECT target_id FROM edges WHERE document_id = ?
                )
            """, (document_id, document_id))
            cursor.execute("DELETE FROM edges WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM executive_summaries WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM narrative_reports WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM risk_simulations WHERE document_id = ?", (document_id,))
            cursor.execute("DELETE FROM documents WHERE id = ?", (document_id,))

        # ChromaDB 0.4.22 raises when collection.delete() matches zero documents.
        # Check first; skip the call if no chunks exist for this document.
        try:
            existing = self.collection.get(where={"document_id": {"$eq": document_id}})
            if existing["ids"]:
                self.collection.delete(where={"document_id": {"$eq": document_id}})
        except Exception as e:
            print(f"[!] Vault: ChromaDB cleanup failed for {document_id}: {e}")
            raise

    def get_friction_lines(self, document_id: str) -> List[Dict[str, Any]]:
        """Retrieves persisted friction lines for a document."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT source_node_id AS source, target_node_id AS target,
                   diamond, provenance_ids, severity, probability, finding_json
            FROM friction_lines WHERE document_id = ?
        """, (document_id,))
        rows = cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["provenance_ids"] = json.loads(d["provenance_ids"])
            finding_json = d.pop("finding_json", None)
            if finding_json:
                d["finding"] = json.loads(finding_json)
            result.append(d)
        return result

    def get_hub_nodes(self, document_id: str, min_dependents: int = 3) -> List[Dict[str, Any]]:
        """
        Returns nodes that are the target of >= min_dependents REQUIRES edges
        within the given document. Each result includes the list of dependent node IDs.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT n.id, n.name, COUNT(e.id) AS dependency_count
            FROM nodes n
            JOIN edges e ON n.id = e.target_id
            WHERE e.relationship = 'REQUIRES' AND e.document_id = ?
            GROUP BY n.id
            HAVING dependency_count >= ?
            ORDER BY dependency_count DESC
        """, (document_id, min_dependents))
        hubs = [dict(row) for row in cursor.fetchall()]

        for hub in hubs:
            cursor.execute("""
                SELECT source_id FROM edges
                WHERE target_id = ? AND relationship = 'REQUIRES' AND document_id = ?
            """, (hub["id"], document_id))
            hub["dependent_node_ids"] = [row["source_id"] for row in cursor.fetchall()]

        return hubs

    def get_node_source_chunk(self, node_id: str, document_id: str) -> Optional[str]:
        """
        Returns the source_chunk_id from any REQUIRES edge that targets this node
        within the given document. Returns None if no such edge exists.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT source_chunk_id FROM edges
            WHERE target_id = ? AND document_id = ? AND relationship = 'REQUIRES'
            LIMIT 1
        """, (node_id, document_id))
        row = cursor.fetchone()
        return row["source_chunk_id"] if row else None

    def get_fragility_lines(self, document_id: str) -> List[Dict[str, Any]]:
        """Retrieves persisted fragility results for a document."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, hub_node_id, dependency_count, insight, cascade_nodes
            FROM fragility_lines WHERE document_id = ?
        """, (document_id,))
        rows = cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["cascade_nodes"] = json.loads(d["cascade_nodes"])
            result.append(d)
        return result

    def get_hub_vulnerabilities(self, document_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Calculates In-Degree Centrality to identify single points of failure.
        Counts all REQUIRES and STARTS_AFTER edges pointing at each node,
        scoped to the given document, ordered by dependency count descending.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                n.id,
                n.name,
                n.label,
                COUNT(e.id) AS dependency_count
            FROM nodes n
            JOIN edges e ON n.id = e.target_id
            WHERE e.relationship IN ('REQUIRES', 'STARTS_AFTER')
              AND e.document_id = ?
            GROUP BY n.id
            ORDER BY dependency_count DESC
            LIMIT ?
        """, (document_id, limit))
        return [dict(row) for row in cursor.fetchall()]

    def get_executive_summary(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Returns the cached plain-English report for a document, or None if not yet generated."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT report_json FROM executive_summaries WHERE document_id = ?",
            (document_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return json.loads(row["report_json"])

    def save_executive_summary(self, document_id: str, report: Dict[str, Any], model: str) -> None:
        """Writes or overwrites the cached plain-English report for a document."""
        generated_at = report.get("generated_at", datetime.now(timezone.utc).isoformat())
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO executive_summaries (document_id, generated_at, model, report_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    generated_at = excluded.generated_at,
                    model        = excluded.model,
                    report_json  = excluded.report_json
                """,
                (document_id, generated_at, model, json.dumps(report))
            )
            self.conn.commit()

    def delete_executive_summary(self, document_id: str) -> None:
        """Removes the cached report for a document. Safe to call even if no cache exists."""
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "DELETE FROM executive_summaries WHERE document_id = ?",
                (document_id,)
            )
            self.conn.commit()

    def upsert_fragility_lines(self, document_id: str, results: List[Dict[str, Any]]) -> None:
        """Persists fragility analysis results to SQLite, replacing any existing rows."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM fragility_lines WHERE document_id = ?", (document_id,))
        for i, r in enumerate(results):
            cursor.execute("""
                INSERT INTO fragility_lines (id, document_id, hub_node_id, dependency_count, insight, cascade_nodes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                f"{document_id}_frag_{i}",
                document_id,
                r["hub_node_id"],
                r.get("dependency_count", 0),
                r["insight"],
                json.dumps(r["cascade_nodes"])
            ))
        self.conn.commit()

    def insert_temporal_data(self, temporal_nodes: List[Dict[str, Any]]) -> None:
        """
        Inserts calculated ISO 8601 dates into the temporal_metadata table.
        Uses INSERT OR REPLACE so a later, more specific date overwrites a fuzzy estimate.
        """
        if not temporal_nodes:
            return
        with self._write_lock:
            cursor = self.conn.cursor()
            try:
                for t_node in temporal_nodes:
                    node_id = t_node.get("node_id")
                    if not node_id:
                        raise ValueError(f"temporal node record missing node_id: {t_node!r}")
                    cursor.execute("""
                        INSERT OR REPLACE INTO temporal_metadata
                        (node_id, start_date, end_date, duration_days, is_milestone)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        node_id,
                        t_node.get("start_date"),
                        t_node.get("end_date"),
                        t_node.get("duration_days"),
                        t_node.get("is_milestone"),
                    ))
                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                print(f"[!] Temporal Insertion Failed: {e}")
                raise

    def get_chronological_friction(self, document_id: str = "") -> List[Dict[str, Any]]:
        """
        Detects Negative Slack: where Node B STARTS_AFTER Node A but B's start_date
        is before A's end_date. Uses pure SQLite date string comparison (ISO 8601 sorts lexicographically).
        Scoped to a document when document_id is provided.
        """
        cursor = self.conn.cursor()
        base_query = """
            SELECT
                e.source_id AS predecessor,
                e.target_id AS successor,
                e.source_chunk_id AS chunk_bridge,
                t1.end_date AS pred_end,
                t2.start_date AS succ_start
            FROM edges e
            JOIN temporal_metadata t1 ON e.source_id = t1.node_id
            JOIN temporal_metadata t2 ON e.target_id = t2.node_id
            WHERE e.relationship = 'STARTS_AFTER'
              AND t2.start_date < t1.end_date
        """
        if document_id:
            cursor.execute(base_query + " AND e.document_id = ?", (document_id,))
        else:
            cursor.execute(base_query)
        return [dict(row) for row in cursor.fetchall()]

    def upsert_chronological_friction_lines(self, document_id: str, lines: List[Dict[str, Any]]) -> None:
        """Persists chronological friction lines to SQLite, replacing any existing rows."""
        cursor = self.conn.cursor()
        try:
            cursor.execute("DELETE FROM chronological_friction_lines WHERE document_id = ?", (document_id,))
            for i, line in enumerate(lines):
                cursor.execute("""
                    INSERT INTO chronological_friction_lines
                    (id, document_id, source_node_id, target_node_id, diamond, provenance_ids, severity, probability, finding_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"{document_id}_cf_{i}",
                    document_id,
                    line["source"],
                    line["target"],
                    line["diamond"],
                    json.dumps(line.get("provenance_ids", [])),
                    line.get("severity", 3),
                    line.get("probability", 3),
                    json.dumps(line["finding"]) if line.get("finding") else None,
                ))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            print(f"[!] Chronological Friction Insertion Failed: {e}")
            raise

    def get_chronological_friction_lines(self, document_id: str) -> List[Dict[str, Any]]:
        """Retrieves persisted chronological friction lines for a document."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT source_node_id AS source, target_node_id AS target,
                   diamond, provenance_ids, severity, probability, finding_json
            FROM chronological_friction_lines WHERE document_id = ?
        """, (document_id,))
        rows = cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["provenance_ids"] = json.loads(d["provenance_ids"])
            finding_json = d.pop("finding_json", None)
            if finding_json:
                d["finding"] = json.loads(finding_json)
            result.append(d)
        return result

    def get_schedule_collapse_forecast(self, document_id: str) -> List[Dict[str, Any]]:
        """
        Returns chronological friction lines enriched with temporal metadata,
        ranked by days of negative slack (how far pred_end overruns succ_start).
        Excludes items where either node lacks temporal data.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT
                pred_node.name                                           AS predecessor_name,
                succ_node.name                                           AS successor_name,
                tm_pred.end_date                                         AS pred_end_date,
                tm_succ.start_date                                       AS succ_start_date,
                ROUND(julianday(tm_pred.end_date) - julianday(tm_succ.start_date)) AS days_at_risk,
                cfl.diamond                                              AS analysis
            FROM chronological_friction_lines cfl
            JOIN nodes pred_node ON cfl.source_node_id = pred_node.id
            JOIN nodes succ_node ON cfl.target_node_id = succ_node.id
            JOIN temporal_metadata tm_pred ON cfl.source_node_id = tm_pred.node_id
            JOIN temporal_metadata tm_succ ON cfl.target_node_id = tm_succ.node_id
            WHERE cfl.document_id = ?
              AND tm_pred.end_date IS NOT NULL
              AND tm_succ.start_date IS NOT NULL
              AND julianday(tm_pred.end_date) > julianday(tm_succ.start_date)
            ORDER BY days_at_risk DESC
        """, (document_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_risk_matrix_data(self, document_id: str) -> List[Dict[str, Any]]:
        """
        Returns all friction items (structural + chronological) with severity and
        probability scores. COALESCE defaults to 3 for pre-migration rows.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 'structural'   AS type,
                   source_node_id AS source,
                   target_node_id AS target,
                   diamond        AS analysis,
                   COALESCE(severity, 3)    AS severity,
                   COALESCE(probability, 3) AS probability
            FROM friction_lines
            WHERE document_id = ?

            UNION ALL

            SELECT 'chronological' AS type,
                   source_node_id  AS source,
                   target_node_id  AS target,
                   diamond         AS analysis,
                   COALESCE(severity, 3)    AS severity,
                   COALESCE(probability, 3) AS probability
            FROM chronological_friction_lines
            WHERE document_id = ?
        """, (document_id, document_id))
        return [dict(row) for row in cursor.fetchall()]

    def save_narrative_report(self, document_id: str, report: dict, model: str) -> None:
        """Writes or overwrites the cached narrative report for a document."""
        generated_at = datetime.now(timezone.utc).isoformat()
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO narrative_reports (document_id, generated_at, model, report_json) VALUES (?, ?, ?, ?)",
                (document_id, generated_at, model, json.dumps(report))
            )
            self.conn.commit()

    def get_narrative_report(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Returns the cached narrative report for a document, or None if not yet generated."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT report_json FROM narrative_reports WHERE document_id = ?",
            (document_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return json.loads(row["report_json"])

    def delete_narrative_report(self, document_id: str) -> None:
        """Removes the cached narrative report for a document. Safe to call even if no cache exists."""
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "DELETE FROM narrative_reports WHERE document_id = ?",
                (document_id,)
            )
            self.conn.commit()

    def save_risk_simulation(self, document_id: str, result: dict) -> None:
        """Writes or overwrites the cached risk simulation result for a document."""
        generated_at = datetime.now(timezone.utc).isoformat()
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO risk_simulations (document_id, generated_at, result_json) VALUES (?, ?, ?)",
                (document_id, generated_at, json.dumps(result))
            )
            self.conn.commit()

    def get_risk_simulation(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Returns the cached risk simulation result for a document, or None if not yet generated."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT result_json FROM risk_simulations WHERE document_id = ?",
            (document_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return json.loads(row["result_json"])

    def delete_risk_simulation(self, document_id: str) -> None:
        """Removes the cached risk simulation for a document. Safe to call even if no cache exists."""
        with self._write_lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "DELETE FROM risk_simulations WHERE document_id = ?",
                (document_id,)
            )
            self.conn.commit()

    def has_temporal_data(self, document_id: str) -> bool:
        """Returns True if any nodes in this document's edges have temporal metadata."""
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT COUNT(*) FROM temporal_metadata
               WHERE node_id IN (
                   SELECT source_id FROM edges WHERE document_id = ?
                   UNION
                   SELECT target_id FROM edges WHERE document_id = ?
               )""",
            (document_id, document_id)
        )
        row = cursor.fetchone()
        return row[0] > 0
