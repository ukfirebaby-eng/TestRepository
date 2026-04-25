import os
import json
import sqlite3
import threading
import chromadb
from datetime import datetime, timezone
from typing import List, Dict, Tuple, Any, Optional


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
                FOREIGN KEY(source_id) REFERENCES nodes(id),
                FOREIGN KEY(target_id) REFERENCES nodes(id)
            )
        """)

        # Traversal Indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_relationship ON edges(relationship)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_edges_document ON edges(document_id)")

        # Documents Table — tracks every ingested document for UI restore
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

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
                        INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (edge_id, document_id, edge['source_id'], edge['target_id'], edge['relationship'], source_chunk_id))

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
                    e2.source_chunk_id AS chunk_blocks
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
                    e2.source_chunk_id AS chunk_blocks
                FROM edges e1
                JOIN edges e2 ON e1.target_id = e2.target_id
                WHERE e1.relationship = 'REQUIRES'
                  AND e2.relationship = 'BLOCKS'
            """
            cursor.execute(query)

        return [dict(row) for row in cursor.fetchall()]

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
                INSERT INTO friction_lines (id, document_id, source_node_id, target_node_id, diamond, provenance_ids, severity, probability)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"{document_id}_fl_{i}",
                document_id,
                fl["source"],
                fl["target"],
                fl["diamond"],
                json.dumps(fl["provenance_ids"]),
                fl.get("severity", 3),
                fl.get("probability", 3),
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
                   diamond, provenance_ids, severity, probability
            FROM friction_lines WHERE document_id = ?
        """, (document_id,))
        rows = cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["provenance_ids"] = json.loads(d["provenance_ids"])
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
                    (id, document_id, source_node_id, target_node_id, diamond, provenance_ids, severity, probability)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"{document_id}_cf_{i}",
                    document_id,
                    line["source"],
                    line["target"],
                    line["diamond"],
                    json.dumps(line.get("provenance_ids", [])),
                    line.get("severity", 3),
                    line.get("probability", 3),
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
                   diamond, provenance_ids, severity, probability
            FROM chronological_friction_lines WHERE document_id = ?
        """, (document_id,))
        rows = cursor.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["provenance_ids"] = json.loads(d["provenance_ids"])
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
