import os
import uuid
import shutil
import asyncio
import json as _json
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from typing import Dict, Any, List
from core.agents import StorytellerAgent, CriticAgent, KDECoverageCheck

# Import our previously written core logic
from core.orchestrator import DiamondOrchestrator
from core.vault import HybridVault

app = FastAPI(title="Diamond Miner API", version="1.0")

# Mount the static folder to serve our Vanilla JS and WebGL UI
os.makedirs("static", exist_ok=True)
app.mount("/assets", StaticFiles(directory="static"), name="static")

# --- Shared Vault Singleton ---
# Single instance shared across all request handlers to avoid multiple
# concurrent PersistentClient connections to the same ChromaDB directory.
vault = HybridVault(tenant_id="local_user_01")

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
