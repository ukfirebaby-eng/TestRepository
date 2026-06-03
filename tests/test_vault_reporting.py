import pytest
from core.vault import HybridVault


@pytest.fixture
def vault(tmp_path):
    v = HybridVault(tenant_id="test_reporting", base_dir=str(tmp_path))
    yield v
    v.conn.close()


def _seed_hub_graph(vault, document_id="doc_hubs"):
    """Seeds a graph where node_b has 2 REQUIRES + 1 STARTS_AFTER = 3 inbound,
    and node_c has 1 REQUIRES = 1 inbound (below any reasonable threshold)."""
    vault.insert_document(document_id, "hub_report_test.pdf")
    cursor = vault.conn.cursor()
    for name in ["node_a", "node_b", "node_c", "node_d", "node_e"]:
        cursor.execute(
            "INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
            (name, "Concept", name.replace("_", " ").title())
        )
    # node_b: 2x REQUIRES + 1x STARTS_AFTER = 3 inbound
    for src, rel in [("node_a", "REQUIRES"), ("node_d", "REQUIRES"), ("node_e", "STARTS_AFTER")]:
        cursor.execute(
            "INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (f"{document_id}_{src}_{rel}_b", document_id, src, "node_b", rel, f"{document_id}_chunk_1")
        )
    # node_c: 1x REQUIRES only
    cursor.execute(
        "INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (f"{document_id}_a_req_c", document_id, "node_a", "node_c", "REQUIRES", f"{document_id}_chunk_1")
    )
    vault.conn.commit()


class TestGetHubVulnerabilities:
    def test_returns_list(self, vault):
        _seed_hub_graph(vault)
        result = vault.get_hub_vulnerabilities("doc_hubs")
        assert isinstance(result, list)

    def test_hub_node_returned_with_correct_count(self, vault):
        _seed_hub_graph(vault)
        result = vault.get_hub_vulnerabilities("doc_hubs")
        assert len(result) == 2
        top = result[0]
        assert top["id"] == "node_b"
        assert top["dependency_count"] == 3

    def test_result_includes_name_and_label(self, vault):
        _seed_hub_graph(vault)
        result = vault.get_hub_vulnerabilities("doc_hubs")
        top = result[0]
        assert top["name"] == "Node B"
        assert top["label"] == "Concept"

    def test_ordered_by_dependency_count_descending(self, vault):
        _seed_hub_graph(vault)
        result = vault.get_hub_vulnerabilities("doc_hubs")
        counts = [r["dependency_count"] for r in result]
        assert counts == sorted(counts, reverse=True)

    def test_limit_respected(self, vault):
        _seed_hub_graph(vault)
        result = vault.get_hub_vulnerabilities("doc_hubs", limit=1)
        assert len(result) == 1

    def test_scoped_to_document(self, vault):
        _seed_hub_graph(vault, "doc_a")
        # Seed a second document with its own hub — should NOT appear in doc_a results
        vault.insert_document("doc_b", "other.pdf")
        cursor = vault.conn.cursor()
        for name in ["b_x", "b_y", "b_z", "b_hub"]:
            cursor.execute(
                "INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
                (name, "Concept", name)
            )
        for src in ["b_x", "b_y", "b_z"]:
            cursor.execute(
                "INSERT OR IGNORE INTO edges (id, document_id, source_id, target_id, relationship, source_chunk_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (f"doc_b_{src}_req_hub", "doc_b", src, "b_hub", "REQUIRES", "doc_b_chunk_1")
            )
        vault.conn.commit()
        result = vault.get_hub_vulnerabilities("doc_a")
        ids = [r["id"] for r in result]
        assert "b_hub" not in ids

    def test_empty_document_returns_empty_list(self, vault):
        vault.insert_document("doc_empty", "empty.pdf")
        result = vault.get_hub_vulnerabilities("doc_empty")
        assert result == []


def _seed_chron_friction_with_dates(vault, document_id="doc_sched"):
    """Seeds nodes, temporal metadata, and a chronological friction line for schedule tests."""
    vault.insert_document(document_id, "sched_test.pdf")
    cursor = vault.conn.cursor()
    # Insert two nodes
    cursor.execute("INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
                   ("pred_node", "Phase", "Phase 1 Delivery"))
    cursor.execute("INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
                   ("succ_node", "Phase", "Phase 2 Kickoff"))
    # Temporal metadata: pred ends 2026-04-15, succ starts 2026-04-01 (14 days overlap)
    cursor.execute("INSERT OR IGNORE INTO temporal_metadata (node_id, start_date, end_date) VALUES (?, ?, ?)",
                   ("pred_node", "2026-03-01", "2026-04-15"))
    cursor.execute("INSERT OR IGNORE INTO temporal_metadata (node_id, start_date, end_date) VALUES (?, ?, ?)",
                   ("succ_node", "2026-04-01", "2026-05-01"))
    # Chronological friction line
    cursor.execute("""
        INSERT OR IGNORE INTO chronological_friction_lines
        (id, document_id, source_node_id, target_node_id, diamond, provenance_ids)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (f"{document_id}_cf_0", document_id, "pred_node", "succ_node",
          "Phase 2 cannot start before Phase 1 finishes.", '[]'))
    vault.conn.commit()


class TestGetScheduleCollapseForecast:
    def test_returns_empty_list_when_no_chron_lines(self, vault):
        vault.insert_document("doc_no_cf", "x.pdf")
        result = vault.get_schedule_collapse_forecast("doc_no_cf")
        assert result == []

    def test_returns_empty_when_no_temporal_metadata(self, vault):
        vault.insert_document("doc_no_tm", "x.pdf")
        cursor = vault.conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
                       ("n1", "C", "Node 1"))
        cursor.execute("INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
                       ("n2", "C", "Node 2"))
        cursor.execute("""
            INSERT OR IGNORE INTO chronological_friction_lines
            (id, document_id, source_node_id, target_node_id, diamond, provenance_ids)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("doc_no_tm_cf_0", "doc_no_tm", "n1", "n2", "conflict", '[]'))
        vault.conn.commit()
        result = vault.get_schedule_collapse_forecast("doc_no_tm")
        assert result == []

    def test_calculates_days_at_risk(self, vault):
        _seed_chron_friction_with_dates(vault)
        result = vault.get_schedule_collapse_forecast("doc_sched")
        assert len(result) == 1
        assert result[0]["days_at_risk"] == 14

    def test_includes_human_readable_names(self, vault):
        _seed_chron_friction_with_dates(vault)
        result = vault.get_schedule_collapse_forecast("doc_sched")
        assert result[0]["predecessor_name"] == "Phase 1 Delivery"
        assert result[0]["successor_name"] == "Phase 2 Kickoff"

    def test_includes_dates_and_analysis(self, vault):
        _seed_chron_friction_with_dates(vault)
        result = vault.get_schedule_collapse_forecast("doc_sched")
        row = result[0]
        assert row["pred_end_date"] == "2026-04-15"
        assert row["succ_start_date"] == "2026-04-01"
        assert "Phase 2" in row["analysis"]

    def test_ordered_by_days_at_risk_descending(self, vault):
        _seed_chron_friction_with_dates(vault)
        # Add a second conflict with smaller overlap (7 days)
        cursor = vault.conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
                       ("pred2", "Phase", "Phase 3"))
        cursor.execute("INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
                       ("succ2", "Phase", "Phase 4"))
        cursor.execute("INSERT OR IGNORE INTO temporal_metadata (node_id, start_date, end_date) VALUES (?, ?, ?)",
                       ("pred2", "2026-06-01", "2026-07-07"))
        cursor.execute("INSERT OR IGNORE INTO temporal_metadata (node_id, start_date, end_date) VALUES (?, ?, ?)",
                       ("succ2", "2026-07-01", "2026-08-01"))
        cursor.execute("""
            INSERT OR IGNORE INTO chronological_friction_lines
            (id, document_id, source_node_id, target_node_id, diamond, provenance_ids)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("doc_sched_cf_1", "doc_sched", "pred2", "succ2", "conflict 2", '[]'))
        vault.conn.commit()
        result = vault.get_schedule_collapse_forecast("doc_sched")
        assert result[0]["days_at_risk"] >= result[1]["days_at_risk"]

    def test_scoped_to_document(self, vault):
        _seed_chron_friction_with_dates(vault, "doc_sched_a")

        # Seed doc_sched_b with distinct node IDs so each document has its own
        # temporal_metadata rows and the isolation boundary is genuinely tested.
        vault.insert_document("doc_sched_b", "sched_test_b.pdf")
        cursor = vault.conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
                       ("pred_node_b", "Phase", "Phase B1 Delivery"))
        cursor.execute("INSERT OR IGNORE INTO nodes (id, label, name) VALUES (?, ?, ?)",
                       ("succ_node_b", "Phase", "Phase B2 Kickoff"))
        cursor.execute("INSERT OR IGNORE INTO temporal_metadata (node_id, start_date, end_date) VALUES (?, ?, ?)",
                       ("pred_node_b", "2026-05-01", "2026-06-15"))
        cursor.execute("INSERT OR IGNORE INTO temporal_metadata (node_id, start_date, end_date) VALUES (?, ?, ?)",
                       ("succ_node_b", "2026-06-01", "2026-07-01"))
        cursor.execute("""
            INSERT OR IGNORE INTO chronological_friction_lines
            (id, document_id, source_node_id, target_node_id, diamond, provenance_ids)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("doc_sched_b_cf_0", "doc_sched_b", "pred_node_b", "succ_node_b",
              "Phase B2 cannot start before Phase B1 finishes.", '[]'))
        vault.conn.commit()

        result_a = vault.get_schedule_collapse_forecast("doc_sched_a")
        result_b = vault.get_schedule_collapse_forecast("doc_sched_b")

        # Each document returns exactly its own single conflict row.
        assert len(result_a) == 1
        assert len(result_b) == 1

        # Neither result bleeds across the document boundary.
        assert result_a[0]["predecessor_name"] == "Phase 1 Delivery"
        assert result_b[0]["predecessor_name"] == "Phase B1 Delivery"


class TestGetRiskMatrixData:
    def test_returns_empty_for_no_friction(self, vault):
        vault.insert_document("doc_rm_empty", "x.pdf")
        assert vault.get_risk_matrix_data("doc_rm_empty") == []

    def test_structural_items_tagged_correctly(self, vault):
        vault.insert_document("doc_rm_s", "x.pdf")
        cursor = vault.conn.cursor()
        cursor.execute("""
            INSERT INTO friction_lines (id, document_id, source_node_id, target_node_id, diamond, provenance_ids, severity, probability)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ("doc_rm_s_fl_0", "doc_rm_s", "s1", "t1", "conflict", '[]', 4, 3))
        vault.conn.commit()
        result = vault.get_risk_matrix_data("doc_rm_s")
        assert len(result) == 1
        assert result[0]["type"] == "structural"

    def test_chronological_items_tagged_correctly(self, vault):
        vault.insert_document("doc_rm_c", "x.pdf")
        cursor = vault.conn.cursor()
        cursor.execute("""
            INSERT INTO chronological_friction_lines (id, document_id, source_node_id, target_node_id, diamond, provenance_ids, severity, probability)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ("doc_rm_c_cf_0", "doc_rm_c", "s1", "t1", "timeline clash", '[]', 5, 4))
        vault.conn.commit()
        result = vault.get_risk_matrix_data("doc_rm_c")
        assert len(result) == 1
        assert result[0]["type"] == "chronological"

    def test_coalesce_defaults_to_3_for_null_values(self, vault):
        vault.insert_document("doc_rm_null", "x.pdf")
        cursor = vault.conn.cursor()
        # Insert without specifying severity/probability (rely on DEFAULT 3)
        cursor.execute("""
            INSERT INTO friction_lines (id, document_id, source_node_id, target_node_id, diamond, provenance_ids)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("doc_rm_null_fl_0", "doc_rm_null", "s1", "t1", "conflict", '[]'))
        vault.conn.commit()
        result = vault.get_risk_matrix_data("doc_rm_null")
        assert result[0]["severity"] == 3
        assert result[0]["probability"] == 3

    def test_stored_severity_probability_returned(self, vault):
        vault.insert_document("doc_rm_scores", "x.pdf")
        cursor = vault.conn.cursor()
        cursor.execute("""
            INSERT INTO friction_lines (id, document_id, source_node_id, target_node_id, diamond, provenance_ids, severity, probability)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ("doc_rm_scores_fl_0", "doc_rm_scores", "s1", "t1", "conflict", '[]', 5, 2))
        vault.conn.commit()
        result = vault.get_risk_matrix_data("doc_rm_scores")
        assert result[0]["severity"] == 5
        assert result[0]["probability"] == 2

    def test_scoped_to_document(self, vault):
        for doc_id in ["doc_rm_x", "doc_rm_y"]:
            vault.insert_document(doc_id, "x.pdf")
            cursor = vault.conn.cursor()
            cursor.execute("""
                INSERT INTO friction_lines (id, document_id, source_node_id, target_node_id, diamond, provenance_ids)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (f"{doc_id}_fl_0", doc_id, "s1", "t1", "conflict", '[]'))
            vault.conn.commit()
        result = vault.get_risk_matrix_data("doc_rm_x")
        assert len(result) == 1


class TestUpsertFrictionLinesWithScores:
    def test_severity_probability_round_trip_friction_lines(self, vault):
        vault.insert_document("doc_score_fl", "x.pdf")
        items = [{"source": "a", "target": "b", "diamond": "conflict",
                  "provenance_ids": [], "severity": 4, "probability": 2}]
        vault.upsert_friction_lines("doc_score_fl", items)
        result = vault.get_friction_lines("doc_score_fl")
        assert result[0]["severity"] == 4
        assert result[0]["probability"] == 2

    def test_severity_probability_round_trip_chron_friction_lines(self, vault):
        vault.insert_document("doc_score_cf", "x.pdf")
        items = [{"source": "a", "target": "b", "diamond": "conflict",
                  "provenance_ids": [], "severity": 5, "probability": 3}]
        vault.upsert_chronological_friction_lines("doc_score_cf", items)
        result = vault.get_chronological_friction_lines("doc_score_cf")
        assert result[0]["severity"] == 5
        assert result[0]["probability"] == 3

    def test_defaults_to_3_when_scores_not_provided(self, vault):
        vault.insert_document("doc_score_default", "x.pdf")
        items = [{"source": "a", "target": "b", "diamond": "conflict", "provenance_ids": []}]
        vault.upsert_friction_lines("doc_score_default", items)
        result = vault.get_friction_lines("doc_score_default")
        assert result[0]["severity"] == 3
        assert result[0]["probability"] == 3

    def test_structured_finding_round_trip_friction_lines(self, vault):
        vault.insert_document("doc_finding_fl", "x.pdf")
        finding = {
            "title": "Audit evidence readiness conflict",
            "risk_type": "evidence readiness",
            "affected_entity": "Orion Programme",
            "blocked_work": "board sign-off",
            "blocking_condition": "approved transaction history",
            "evidence_summary": "Evidence is produced before source data is approved.",
            "why_it_matters": "Board sign-off could rely on invalid evidence.",
            "recommended_action": "Make approved source data a hard entry criterion.",
            "confidence": 0.88,
            "assumptions": [],
        }
        vault.upsert_friction_lines("doc_finding_fl", [{
            "source": "programme",
            "target": "programme",
            "diamond": "legacy analysis",
            "provenance_ids": ["chunk_1"],
            "finding": finding,
        }])

        result = vault.get_friction_lines("doc_finding_fl")

        assert result[0]["finding"] == finding

    def test_structured_finding_round_trip_chronological_friction_lines(self, vault):
        vault.insert_document("doc_finding_cf", "x.pdf")
        finding = {
            "title": "Launch starts before DR completion",
            "risk_type": "timeline",
            "affected_entity": "Public Launch",
            "blocked_work": "Public Launch",
            "blocking_condition": "Identity Token Service DR",
            "evidence_summary": "Launch starts before DR completes.",
            "why_it_matters": "Launch readiness would be unsupported.",
            "recommended_action": "Move launch until after DR sign-off.",
            "confidence": 0.9,
            "assumptions": [],
        }
        vault.upsert_chronological_friction_lines("doc_finding_cf", [{
            "source": "dr",
            "target": "launch",
            "diamond": "legacy timeline analysis",
            "provenance_ids": ["chunk_2"],
            "finding": finding,
        }])

        result = vault.get_chronological_friction_lines("doc_finding_cf")

        assert result[0]["finding"] == finding
