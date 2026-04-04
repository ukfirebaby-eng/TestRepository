import os
import uuid
import shutil
import asyncio
import json as _json
import datetime
from io import BytesIO
from pathlib import Path
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from typing import Dict, Any, List, Literal
from core.agents import StorytellerAgent, CriticAgent, KDECoverageCheck, OutlineAgent, RecursiveDraftingAgent, ContradictionHunterAgent
from core.simulator import BlastRadiusCalculator, BlackSwanAgent, MonteCarloForecaster
from core.report_assembler import ReportAssembler

# Import our previously written core logic
from core.orchestrator import DiamondOrchestrator
from core.vault import HybridVault
from core.config import read_env, write_env, mask_key
from pydantic import BaseModel
from dotenv import load_dotenv

app = FastAPI(title="Diamond Miner API", version="1.0")

# Mount the static folder to serve our Vanilla JS and WebGL UI
os.makedirs("static", exist_ok=True)
app.mount("/assets", StaticFiles(directory="static"), name="static")

# --- Shared Vault Singleton ---
# Single instance shared across all request handlers to avoid multiple
# concurrent PersistentClient connections to the same ChromaDB directory.
vault = HybridVault(
    tenant_id="local_user_01",
    base_dir=os.getenv("VAULT_PATH", "./vaults"),
)

# --- In-Memory Job Store ---
# For a local desktop app, a simple dictionary is perfect for tracking async jobs.
# (If we were deploying to AWS, we'd swap this for Redis)
JOB_STORE: Dict[str, Dict[str, Any]] = {}

# --- In-Memory Document Store ---
# Maps document_id -> {"friction_lines": [...], "chronological_friction_lines": [...]}
DOCUMENT_STORE: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

# --- In-flight generation tracker ---
# Prevents concurrent generation for the same document.
# Safe as a plain set — FastAPI's async loop is single-threaded.
_active_generations: set = set()

# --- In-flight narrative generation tracker ---
_active_narratives: set = set()

# --- In-flight risk simulation tracker ---
_active_simulations: set = set()

# --- In-flight mitigation tracker ---
_active_mitigations: set[str] = set()


def _env_path() -> Path:
    """Returns the path to the .env file co-located with api.py."""
    return Path(__file__).parent / ".env"


def _run_ingestion_task(job_id: str, file_path: str, tenant_id: str, document_id: str, document_name: str):
    """The background worker that executes the Orchestrator without freezing the API."""
    try:
        JOB_STORE[job_id]["status"] = "processing"

        def _log(msg: str):
            JOB_STORE[job_id]["log"].append(msg)

        orchestrator = DiamondOrchestrator(tenant_id=tenant_id, document_id=document_id, document_name=document_name, vault=vault, log_fn=_log)
        orchestrator.run_ingestion_pipeline(file_path=file_path)

        friction_lines = orchestrator.interrogate_friction()
        orchestrator.interrogate_fragility()
        time_friction_lines = orchestrator.interrogate_time_friction()

        DOCUMENT_STORE[document_id] = {
            "friction_lines": friction_lines,
            "chronological_friction_lines": time_friction_lines,
        }

        JOB_STORE[job_id]["status"] = "completed"
        JOB_STORE[job_id]["friction_lines"] = friction_lines

    except Exception as e:
        print(f"[!] Background Task Failed: {e}")
        JOB_STORE[job_id]["status"] = "failed"
        JOB_STORE[job_id]["error"] = str(e)


def _gather_raw_issues(document_id: str) -> dict:
    """Collates all raw issue data from the vault for the Storyteller prompt."""
    return {
        "friction_lines": vault.get_friction_lines(document_id),
        "chronological_friction_lines": vault.get_chronological_friction_lines(document_id),
        "hub_vulnerabilities": vault.get_hub_vulnerabilities(document_id),
        "risk_matrix": vault.get_risk_matrix_data(document_id),
    }


# --- UI Route ---
@app.get("/")
async def serve_ui():
    """Serves the main WebGL Spatial Canvas application."""
    ui_path = "static/index.html"
    if not os.path.exists(ui_path):
        raise HTTPException(status_code=404, detail="UI not found. Please create static/index.html")
    return FileResponse(ui_path)


# --- API Routes ---
@app.post("/api/v1/ingest")
async def ingest_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Accepts a PDF, assigns a job ID, and hands it off to a background thread."""
    job_id = str(uuid.uuid4())
    document_id = f"doc_{uuid.uuid4().hex[:8]}"
    tenant_id = "local_user_01"  # Hardcoded for the local desktop version

    # Save the uploaded file temporarily so PyMuPDF can read it
    temp_dir = "./temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Reject unsupported file types before spending any further resources
    _ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx", ".xlsx", ".csv", ".pptx"}
    ext = Path(file.filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        os.remove(file_path)
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )

    # Register the job
    JOB_STORE[job_id] = {"status": "pending", "document_id": document_id, "log": []}

    # Fire and forget
    background_tasks.add_task(_run_ingestion_task, job_id, file_path, tenant_id, document_id, file.filename)

    return {"job_id": job_id, "document_id": document_id, "status": "pending"}


@app.get("/api/v1/status/{job_id}")
async def get_job_status(job_id: str):
    """The frontend polls this endpoint every 1s to update the loading screen."""
    if job_id not in JOB_STORE:
        raise HTTPException(status_code=404, detail="Job not found")
    return JOB_STORE[job_id]


@app.get("/api/v1/documents")
async def list_documents():
    """Returns all previously ingested documents so the UI can restore them without re-processing."""
    return {"documents": vault.list_documents()}


@app.delete("/api/v1/documents/{document_id}")
async def delete_document_endpoint(document_id: str):
    """Permanently deletes a document and all its associated vault data."""
    cursor = vault.conn.cursor()

    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    is_processing = any(
        job.get("document_id") == document_id and job.get("status") == "processing"
        for job in JOB_STORE.values()
    )
    if is_processing:
        raise HTTPException(status_code=409, detail="Document ingestion is still in progress.")

    try:
        vault.delete_document(document_id)
        DOCUMENT_STORE.pop(document_id, None)
        return {"status": "deleted", "document_id": document_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/vault", status_code=200)
async def clear_vault():
    """Wipes all documents, graph data, analysis results, and report caches."""
    if _active_generations or _active_narratives or _active_simulations:
        raise HTTPException(status_code=409, detail="Generation in progress — cancel before clearing.")
    try:
        vault.clear_all()
        DOCUMENT_STORE.clear()
        JOB_STORE.clear()
        return {"status": "cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/reports/friction-queue/{document_id}")
async def get_friction_queue(document_id: str):
    """
    Delivers the ITDO Operational Dashboard.
    Returns all structural and chronological friction lines for a document,
    tagged with their type. Uses persisted vault data — works after server restart.
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    structural = [
        {**line, "type": "structural"}
        for line in vault.get_friction_lines(document_id)
    ]
    chronological = [
        {**line, "type": "chronological"}
        for line in vault.get_chronological_friction_lines(document_id)
    ]
    return {"friction_queue": structural + chronological}


@app.get("/api/v1/reports/bottlenecks/{document_id}")
async def get_bottlenecks(document_id: str):
    """
    Delivers the Hub & Spoke Tactical Dashboard.
    Returns the top 5 nodes by in-degree centrality (REQUIRES + STARTS_AFTER).
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    vulnerabilities = vault.get_hub_vulnerabilities(document_id, limit=5)
    return {"bottlenecks": vulnerabilities}


@app.get("/api/v1/reports/schedule-collapse/{document_id}")
async def get_schedule_collapse(document_id: str):
    """
    Returns chronological friction lines ranked by days of negative slack.
    Excludes rows where either node lacks temporal metadata.
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"schedule_collapse": vault.get_schedule_collapse_forecast(document_id)}


@app.get("/api/v1/reports/risk-matrix/{document_id}")
async def get_risk_matrix(document_id: str):
    """
    Returns all friction items (structural + chronological) with severity
    and probability scores, suitable for rendering a 5x5 risk matrix.
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"risk_matrix": vault.get_risk_matrix_data(document_id)}


@app.get("/api/v1/reports/executive-summary/{document_id}")
async def get_executive_summary(document_id: str):
    """
    Returns the cached plain-English executive report for a document.
    Returns {"cached": false} if the document exists but report has not been generated yet.
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    cached = vault.get_executive_summary(document_id)
    if cached is None:
        return {"cached": False}
    return {"cached": True, "report": cached}


@app.post("/api/v1/reports/executive-summary/{document_id}")
async def generate_executive_summary(document_id: str):
    """
    Triggers multi-agent plain-English report generation and streams progress via SSE.
    Caches the completed report in SQLite. Returns 409 if already generating.
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    if document_id in _active_generations:
        raise HTTPException(status_code=409, detail="Report generation already in progress for this document.")

    # Add synchronously in the endpoint body — before the generator starts —
    # so no two requests can both pass the 409 guard in the same event loop tick.
    _active_generations.add(document_id)

    async def _stream():
        try:
            yield f"data: {_json.dumps({'stage': 'analysing', 'message': 'Analysing issues...'})}\n\n"
            raw_issues = await asyncio.to_thread(_gather_raw_issues, document_id)

            yield f"data: {_json.dumps({'stage': 'drafting', 'message': 'Drafting plain-English narrative...'})}\n\n"
            storyteller = StorytellerAgent()
            draft = await asyncio.to_thread(storyteller.run, raw_issues)

            yield f"data: {_json.dumps({'stage': 'auditing', 'message': 'Auditing for omissions...'})}\n\n"
            critic = CriticAgent()
            audited = await asyncio.to_thread(critic.run, draft, raw_issues, storyteller)

            yield f"data: {_json.dumps({'stage': 'verifying', 'message': 'Verifying coverage...'})}\n\n"
            kde = KDECoverageCheck(vault)
            final = await asyncio.to_thread(kde.check, document_id, audited)

            vault.save_executive_summary(document_id, final, storyteller.model)
            yield f"data: {_json.dumps({'stage': 'complete', 'report': final})}\n\n"
        finally:
            _active_generations.discard(document_id)

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.delete("/api/v1/reports/executive-summary/{document_id}", status_code=204)
async def delete_executive_summary(document_id: str):
    """
    Clears the cached executive report for a document (called by the Regenerate button).
    Returns 204 even if no cached row exists — idempotent.
    Returns 404 only if the document_id does not exist at all.
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    vault.delete_executive_summary(document_id)


def assemble_narrative(chapters: list, raw_issues: dict) -> dict:
    """
    Assembles chapter drafts + raw issues into the final narrative report dict.
    Builds a flat issues list (Critic/KDE compatible) by resolving chapter indices
    against the concatenated friction_lines + chronological_friction_lines + hub_vulnerabilities.
    """
    flat_issues = (
        raw_issues.get("friction_lines", [])
        + raw_issues.get("chronological_friction_lines", [])
        + raw_issues.get("hub_vulnerabilities", [])
    )

    issues: list = []
    for chapter in chapters:
        for idx in chapter.get("indices", []):
            if 0 <= idx < len(flat_issues):
                issues.append(flat_issues[idx])

    if not flat_issues:
        overall_assessment = "No Issues Found"
    else:
        severities = [i.get("severity", 0) for i in flat_issues if isinstance(i.get("severity"), (int, float))]
        max_severity = max(severities) if severities else 0
        if max_severity >= 5:
            overall_assessment = "Critical Risk"
        elif max_severity >= 4:
            overall_assessment = "High Risk"
        elif max_severity >= 3:
            overall_assessment = "Moderate Risk"
        else:
            overall_assessment = "Low Risk"

    return {
        "overall_assessment": overall_assessment,
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "executive_summary": "",
        "chapters": chapters,
        "issues": issues,
        "coverage_verified": False,
        "coverage_warning": None,
    }


@app.get("/api/v1/canvas/{document_id}")
async def get_canvas_data(document_id: str):
    """Returns the unified graph topology for the WebGL renderer."""
    try:
        cursor = vault.conn.cursor()

        # 404 if document does not exist
        cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Document not found.")

        cursor.execute("""
            SELECT DISTINCT n.id, n.label, n.name FROM nodes n
            WHERE n.id IN (
                SELECT source_id FROM edges WHERE document_id = ?
                UNION
                SELECT target_id FROM edges WHERE document_id = ?
            )
        """, (document_id, document_id))
        nodes = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT source_id AS source, target_id AS target, relationship, source_chunk_id
            FROM edges WHERE document_id = ?
        """, (document_id,))
        edges = [dict(row) for row in cursor.fetchall()]

        # Retrieve temporal node metadata scoped to this document's nodes only
        cursor.execute("""
            SELECT tm.node_id, tm.start_date, tm.end_date
            FROM temporal_metadata tm
            WHERE tm.node_id IN (
                SELECT source_id FROM edges WHERE document_id = ?
                UNION
                SELECT target_id FROM edges WHERE document_id = ?
            )
        """, (document_id, document_id))
        temporal_by_node = {row["node_id"]: dict(row) for row in cursor.fetchall()}

        # Enrich nodes with temporal metadata
        enriched_nodes = []
        for node in nodes:
            t = temporal_by_node.get(node["id"], {})
            enriched_nodes.append({**node, **t})

        # Retrieve persisted or in-memory chronological friction
        doc_store = DOCUMENT_STORE.get(document_id, {})
        chronological_friction_lines = (
            vault.get_chronological_friction_lines(document_id)
            or doc_store.get("chronological_friction_lines", [])
        )
        friction_lines_from_store = doc_store.get("friction_lines", [])

        friction_lines = vault.get_friction_lines(document_id) or friction_lines_from_store
        fragility_lines = vault.get_fragility_lines(document_id)

        return {
            "document_id": document_id,
            "nodes": enriched_nodes,
            "edges": edges,
            "friction_lines": friction_lines,
            "fragility_lines": fragility_lines,
            "chronological_friction_lines": chronological_friction_lines,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/reports/narrative/{document_id}")
async def get_narrative_report(document_id: str):
    """Returns the cached narrative report, or {"cached": False} if not yet generated."""
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    cached = vault.get_narrative_report(document_id)
    if cached is None:
        return {"cached": False}
    return {"cached": True, "report": cached}


@app.post("/api/v1/reports/narrative/{document_id}")
async def generate_narrative_report(document_id: str):
    """
    Triggers multi-chapter narrative report generation and streams progress via SSE.
    Uses OutlineAgent + RecursiveDraftingAgent (or StorytellerAgent fallback).
    Returns 409 if already generating.
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    if document_id in _active_narratives:
        raise HTTPException(status_code=409, detail="Narrative generation already in progress for this document.")

    async def _stream():
        _active_narratives.add(document_id)
        try:
            yield f"data: {_json.dumps({'stage': 'analysing', 'message': 'Analysing issues...'})}\n\n"
            raw_issues = await asyncio.to_thread(_gather_raw_issues, document_id)

            yield f"data: {_json.dumps({'stage': 'outlining', 'message': 'Identifying thematic chapters\u2026'})}\n\n"
            outline = await asyncio.to_thread(OutlineAgent().run, raw_issues)

            if len(outline) <= 1:
                storyteller = StorytellerAgent()
                draft = await asyncio.to_thread(storyteller.run, raw_issues)
                drafter_or_storyteller = storyteller
            else:
                drafter = RecursiveDraftingAgent(raw_issues)
                chapters = []
                rolling = ""
                for i, chapter_outline in enumerate(outline):
                    chapter_title = chapter_outline.get("title", f"Chapter {i + 1}")
                    n = len(outline)
                    yield f"data: {_json.dumps({'stage': f'drafting_{i + 1}_of_{n}', 'message': f'Writing chapter {i + 1} of {n}: {chapter_title}\u2026'})}\n\n"
                    result = await asyncio.to_thread(drafter.run, chapter_outline, rolling)
                    chapters.append(result)
                    rolling = "; ".join(f"{c['title']}: {c['narrative'][:120]}" for c in chapters)
                draft = assemble_narrative(chapters, raw_issues)
                drafter_or_storyteller = drafter

            yield f"data: {_json.dumps({'stage': 'auditing', 'message': 'Auditing for omissions\u2026'})}\n\n"
            audited = await asyncio.to_thread(CriticAgent().run, draft, raw_issues, drafter_or_storyteller)

            yield f"data: {_json.dumps({'stage': 'verifying', 'message': 'Verifying coverage\u2026'})}\n\n"
            final = await asyncio.to_thread(KDECoverageCheck(vault).check, document_id, audited)

            vault.save_narrative_report(document_id, final, drafter_or_storyteller.model)
            yield f"data: {_json.dumps({'stage': 'complete', 'report': final})}\n\n"
        finally:
            _active_narratives.discard(document_id)

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.delete("/api/v1/reports/narrative/{document_id}", status_code=204)
async def delete_narrative_report(document_id: str):
    """
    Clears the cached narrative report for a document. Idempotent — 204 even if no cached row.
    Returns 404 only if the document_id does not exist at all.
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    vault.delete_narrative_report(document_id)


@app.get("/api/v1/reports/risk-simulation/{document_id}")
async def get_risk_simulation(document_id: str):
    """Returns the cached risk simulation result, or {"cached": False} if not yet generated."""
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    cached = vault.get_risk_simulation(document_id)
    if cached is None:
        return {"cached": False}
    return {"cached": True, "result": cached}


@app.post("/api/v1/reports/risk-simulation/{document_id}")
async def generate_risk_simulation(document_id: str):
    """
    Triggers blast-radius, black-swan, and Monte Carlo simulation and streams progress via SSE.
    Caches the completed result in the vault. Returns 409 if already simulating.
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    if document_id in _active_simulations:
        raise HTTPException(status_code=409, detail="Risk simulation already in progress for this document.")

    async def _stream():
        _active_simulations.add(document_id)
        try:
            yield f"data: {_json.dumps({'stage': 'blast_radius', 'message': 'Calculating blast radius\u2026'})}\n\n"
            blast = await asyncio.to_thread(BlastRadiusCalculator(document_id, vault).run)

            yield f"data: {_json.dumps({'stage': 'black_swan', 'message': 'Generating stress scenarios\u2026'})}\n\n"
            black_swan = await asyncio.to_thread(BlackSwanAgent(document_id, vault).run)

            yield f"data: {_json.dumps({'stage': 'monte_carlo', 'message': 'Running 5,000 timeline trials\u2026'})}\n\n"
            forecast = await asyncio.to_thread(MonteCarloForecaster(document_id, vault).run)

            final_result = {"blast_radius": blast, "black_swan": black_swan, "monte_carlo": forecast}
            vault.save_risk_simulation(document_id, final_result)
            yield f"data: {_json.dumps({'stage': 'complete', 'result': final_result})}\n\n"
        finally:
            _active_simulations.discard(document_id)

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.delete("/api/v1/reports/risk-simulation/{document_id}", status_code=204)
async def delete_risk_simulation(document_id: str):
    """
    Clears the cached risk simulation for a document. Idempotent — 204 even if no cached row.
    Returns 404 only if the document_id does not exist at all.
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    vault.delete_risk_simulation(document_id)


@app.post("/api/v1/reports/mitigation/{document_id}")
async def generate_mitigation(
    document_id: str,
    source_node_id: str = Query(...),
    target_node_id: str = Query(...),
):
    """
    Streams a targeted mitigation for a specific friction item identified by
    source_node_id + target_node_id. Checks structural friction_lines first,
    then chronological_friction_lines. Returns 404 if either the document or
    the friction item is not found.
    """
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    cursor2 = vault.conn.cursor()
    cursor2.execute(
        "SELECT diamond, provenance_ids FROM friction_lines "
        "WHERE document_id=? AND source_node_id=? AND target_node_id=?",
        (document_id, source_node_id, target_node_id),
    )
    row = cursor2.fetchone()
    if row is None:
        cursor3 = vault.conn.cursor()
        cursor3.execute(
            "SELECT diamond, provenance_ids FROM chronological_friction_lines "
            "WHERE document_id=? AND source_node_id=? AND target_node_id=?",
            (document_id, source_node_id, target_node_id),
        )
        row = cursor3.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Friction item not found.")

    diamond = row["diamond"]
    provenance_ids = _json.loads(row["provenance_ids"])

    mitigation_key = f"{document_id}:{source_node_id}:{target_node_id}"
    if mitigation_key in _active_mitigations:
        raise HTTPException(status_code=409, detail="Mitigation already in progress for this friction item.")

    async def _stream():
        _active_mitigations.add(mitigation_key)
        try:
            yield f"data: {_json.dumps({'stage': 'analysing', 'message': 'Analysing friction item\u2026'})}\n\n"

            source_texts = []
            for chunk_id in provenance_ids:
                chunk = vault.get_chunk_provenance(chunk_id)
                if chunk.get("text"):
                    source_texts.append(chunk["text"])
            source_text = "\n\n---\n\n".join(source_texts) or "No source text available."

            result = await asyncio.to_thread(
                ContradictionHunterAgent.synthesize_mitigation,
                diamond,
                source_text,
            )
            analysis = result.get("analysis", "No mitigation available.")
            yield f"data: {_json.dumps({'token': analysis})}\n\n"
        except Exception as exc:
            yield f"data: {_json.dumps({'error': str(exc)})}\n\n"
        finally:
            _active_mitigations.discard(mitigation_key)

    return StreamingResponse(content=_stream(), media_type="text/event-stream")


# --- Report Export Endpoints ---

@app.get("/api/v1/export/pdf/{document_id}")
async def export_pdf(document_id: str):
    """Renders the full narrative report as a styled PDF and streams it as a download."""
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    if vault.get_narrative_report(document_id) is None:
        raise HTTPException(status_code=409, detail="Generate the narrative report first.")

    assembler = ReportAssembler(vault)
    payload = assembler.assemble(document_id)

    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("narrative_report.html")
    html_string = template.render(**payload)

    import weasyprint
    pdf_bytes = await asyncio.to_thread(
        weasyprint.HTML(string=html_string).write_pdf
    )

    file_stream = BytesIO(pdf_bytes)
    safe_name = payload["metadata"]["document_name"].replace(" ", "_").replace("/", "_")
    return StreamingResponse(
        file_stream,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Diamond_Miner_Report_{safe_name}.pdf"'},
    )


@app.get("/api/v1/export/docx/{document_id}")
async def export_docx(document_id: str):
    """Renders the full narrative report as a Word document and streams it as a download."""
    cursor = vault.conn.cursor()
    cursor.execute("SELECT id FROM documents WHERE id = ?", (document_id,))
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    if vault.get_narrative_report(document_id) is None:
        raise HTTPException(status_code=409, detail="Generate the narrative report first.")

    assembler = ReportAssembler(vault)
    payload = assembler.assemble(document_id)

    from docxtpl import DocxTemplate
    template_path = os.path.join("templates", "narrative_report.docx")
    if not os.path.exists(template_path):
        raise HTTPException(status_code=500, detail="Word template not found. Contact support.")

    tpl = DocxTemplate(template_path)
    await asyncio.to_thread(tpl.render, payload)

    file_stream = BytesIO()
    tpl.save(file_stream)
    file_stream.seek(0)

    safe_name = payload["metadata"]["document_name"].replace(" ", "_").replace("/", "_")
    return StreamingResponse(
        file_stream,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="Diamond_Miner_Report_{safe_name}.docx"'},
    )


@app.get("/api/v1/config")
async def get_config():
    """Returns current .env values; API keys masked to first 12 chars."""
    vals = read_env(_env_path())
    return {
        "LLM_PROVIDER":        vals.get("LLM_PROVIDER", ""),
        "OPENAI_API_KEY":      mask_key(vals.get("OPENAI_API_KEY", "")),
        "OPENROUTER_API_KEY":  mask_key(vals.get("OPENROUTER_API_KEY", "")),
        "FAST_MODEL":          vals.get("FAST_MODEL", ""),
        "SMART_MODEL":         vals.get("SMART_MODEL", ""),
        "VAULT_PATH":          vals.get("VAULT_PATH", ""),
    }


class ConfigUpdate(BaseModel):
    LLM_PROVIDER: Literal["openai", "openrouter"]
    OPENAI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    FAST_MODEL: str = ""
    SMART_MODEL: str = ""
    VAULT_PATH: str = ""


def _resolve_key(submitted: str, existing: str) -> str:
    """If submitted value is a masked stub (ends with …), return the existing value."""
    if submitted.endswith("\u2026") and len(submitted) == 13 and existing.startswith(submitted[:12]):
        return existing
    return submitted


@app.post("/api/v1/config")
async def update_config(body: ConfigUpdate):
    """Writes .env and hot-reloads env vars without restarting the server."""
    env_path = _env_path()
    existing = read_env(env_path)
    values = {
        "LLM_PROVIDER":       body.LLM_PROVIDER,
        "OPENAI_API_KEY":     _resolve_key(body.OPENAI_API_KEY,     existing.get("OPENAI_API_KEY", "")),
        "OPENROUTER_API_KEY": _resolve_key(body.OPENROUTER_API_KEY, existing.get("OPENROUTER_API_KEY", "")),
        "FAST_MODEL":         body.FAST_MODEL,
        "SMART_MODEL":        body.SMART_MODEL,
        "VAULT_PATH":         body.VAULT_PATH,
    }
    write_env(env_path, values)
    load_dotenv(dotenv_path=env_path, override=True)
    return {"status": "applied"}
