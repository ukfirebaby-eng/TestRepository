"""
Unified Story Dashboard – HTTP server.

Serves a self-contained HTML page that auto-refreshes every 3 seconds and
shows three panes:

  1. Jobs – current status, next/last run, retry state, run count.
  2. Timeline – all JobResult records from every job, sorted newest-first,
     forming the unified "story" of scheduler activity.
  3. Dependency Graph – ASCII representation of the dependency edges.

The server is backed by a single-threaded BaseHTTPServer running in a daemon
thread so it does not interfere with the scheduler's thread pool.
"""

import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.parse import urlparse

# Local import – avoids circular dependency at import time
from scheduler.job import JobStatus


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="3">
  <title>Job Scheduler Dashboard</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      font-family: system-ui, -apple-system, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      margin: 0;
      padding: 1.5rem;
    }}
    h1 {{ color: #7dd3fc; margin: 0 0 0.25rem; font-size: 1.5rem; }}
    .subtitle {{ color: #64748b; font-size: 0.85rem; margin-bottom: 1.5rem; }}
    h2 {{ color: #94a3b8; font-size: 1rem; margin: 1.5rem 0 0.5rem; text-transform: uppercase;
          letter-spacing: 0.08em; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
    th {{ text-align: left; color: #64748b; padding: 0.4rem 0.6rem;
          border-bottom: 1px solid #1e293b; font-weight: 600; }}
    td {{ padding: 0.4rem 0.6rem; border-bottom: 1px solid #1e293b; vertical-align: top; }}
    tr:hover td {{ background: #1e293b; }}
    .badge {{
      display: inline-block; padding: 0.15rem 0.5rem;
      border-radius: 9999px; font-size: 0.75rem; font-weight: 600;
    }}
    .pending   {{ background: #1e3a5f; color: #7dd3fc; }}
    .running   {{ background: #1c3327; color: #4ade80; }}
    .completed {{ background: #1a2e1a; color: #86efac; }}
    .failed    {{ background: #3b1515; color: #fca5a5; }}
    .expired   {{ background: #1e1b4b; color: #a5b4fc; }}
    .ok  {{ color: #4ade80; }}
    .err {{ color: #f87171; }}
    .mono {{ font-family: 'Courier New', monospace; font-size: 0.8rem; color: #94a3b8; }}
    .deps {{ color: #f59e0b; font-size: 0.8rem; }}
    pre {{
      background: #1e293b; border-radius: 0.5rem; padding: 1rem;
      font-size: 0.8rem; color: #94a3b8; overflow-x: auto;
      margin: 0;
    }}
    .section {{ background: #111827; border-radius: 0.5rem; padding: 1rem; margin-bottom: 1rem; }}
    .refreshed {{ color: #475569; font-size: 0.75rem; float: right; margin-top: 0.1rem; }}
  </style>
</head>
<body>
  <h1>Job Scheduler &ndash; Unified Story Dashboard</h1>
  <div class="subtitle">
    Auto-refreshes every 3&nbsp;s &nbsp;&middot;&nbsp;
    <span class="refreshed">Last updated: {refreshed}</span>
  </div>

  <!-- ── Jobs table ───────────────────────────────────────────────── -->
  <div class="section">
    <h2>Jobs ({job_count})</h2>
    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Status</th>
          <th>Schedule</th>
          <th>Next Run</th>
          <th>Last Run</th>
          <th>Runs</th>
          <th>Retries</th>
          <th>Dependencies</th>
        </tr>
      </thead>
      <tbody>
        {jobs_rows}
      </tbody>
    </table>
  </div>

  <!-- ── Timeline ─────────────────────────────────────────────────── -->
  <div class="section">
    <h2>Execution Timeline ({event_count} events)</h2>
    <table>
      <thead>
        <tr>
          <th>Time</th>
          <th>Job</th>
          <th>Result</th>
          <th>Duration</th>
          <th>Detail</th>
        </tr>
      </thead>
      <tbody>
        {timeline_rows}
      </tbody>
    </table>
  </div>

  <!-- ── Dependency graph ──────────────────────────────────────────── -->
  <div class="section">
    <h2>Dependency Graph</h2>
    <pre>{dep_graph}</pre>
  </div>
</body>
</html>
"""

_NO_EVENTS = '<tr><td colspan="5" style="color:#475569;text-align:center">No executions yet</td></tr>'
_NO_JOBS   = '<tr><td colspan="8" style="color:#475569;text-align:center">No jobs registered</td></tr>'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STATUS_CLASS = {
    JobStatus.PENDING:   "pending",
    JobStatus.RUNNING:   "running",
    JobStatus.COMPLETED: "completed",
    JobStatus.FAILED:    "failed",
    JobStatus.EXPIRED:   "expired",
}


def _fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return '<span style="color:#475569">—</span>'
    return f'<span class="mono">{dt.strftime("%H:%M:%S")}</span>'


def _fmt_duration(started_at: datetime, finished_at: datetime) -> str:
    secs = (finished_at - started_at).total_seconds()
    if secs < 1:
        return f"{secs * 1000:.0f}&nbsp;ms"
    return f"{secs:.2f}&nbsp;s"


def _build_dep_graph(jobs) -> str:
    """Return a simple ASCII dependency graph."""
    if not jobs:
        return "(no jobs)"

    lines = []
    for job in jobs:
        if job.dependencies:
            for dep in job.dependencies:
                lines.append(f"  {dep}  -->  {job.name}")
        else:
            # Check if anything depends on this job
            has_dependents = any(job.name in j.dependencies for j in jobs)
            if not has_dependents:
                lines.append(f"  {job.name}  (standalone)")
            else:
                lines.append(f"  {job.name}  (root)")

    return "\n".join(lines) if lines else "(no dependencies)"


def _escape(text: str) -> str:
    """Minimal HTML escaping."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class _DashboardHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests for the dashboard."""

    # Injected by DashboardServer
    scheduler = None

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/jobs":
            self._serve_json()
        elif parsed.path in ("/", "/dashboard"):
            self._serve_html()
        else:
            self.send_error(404, "Not Found")

    def _serve_html(self):
        body = self._render_html().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_json(self):
        """Serve job data as JSON (useful for external integrations)."""
        jobs = self.scheduler.list_jobs() if self.scheduler else []
        data = []
        for job in jobs:
            data.append({
                "name": job.name,
                "status": job.status.value,
                "schedule": job.schedule.description(),
                "next_run": job.next_run.isoformat() if job.next_run else None,
                "last_run": job.last_run.isoformat() if job.last_run else None,
                "run_count": len(job.history),
                "retry_count": job.retry_count,
                "max_retries": job.max_retries,
                "dependencies": job.dependencies,
            })
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _render_html(self) -> str:
        jobs = self.scheduler.list_jobs() if self.scheduler else []

        # ── Jobs rows ────────────────────────────────────────────────
        if jobs:
            rows = []
            for job in jobs:
                status_cls = _STATUS_CLASS.get(job.status, "pending")
                deps_html = (
                    ", ".join(f'<span class="deps">{_escape(d)}</span>' for d in job.dependencies)
                    if job.dependencies else '<span style="color:#475569">—</span>'
                )
                rows.append(
                    f"<tr>"
                    f"<td><strong>{_escape(job.name)}</strong></td>"
                    f'<td><span class="badge {status_cls}">{job.status.value}</span></td>'
                    f'<td class="mono">{_escape(job.schedule.description())}</td>'
                    f"<td>{_fmt_dt(job.next_run)}</td>"
                    f"<td>{_fmt_dt(job.last_run)}</td>"
                    f'<td class="mono">{len(job.history)}</td>'
                    f'<td class="mono">{job.retry_count}/{job.max_retries}</td>'
                    f"<td>{deps_html}</td>"
                    f"</tr>"
                )
            jobs_rows = "\n".join(rows)
        else:
            jobs_rows = _NO_JOBS

        # ── Timeline rows ────────────────────────────────────────────
        all_results = []
        for job in jobs:
            for result in job.history:
                all_results.append(result)

        # Sort newest first
        all_results.sort(key=lambda r: r.finished_at, reverse=True)

        if all_results:
            rows = []
            for result in all_results:
                result_cls = "ok" if result.success else "err"
                result_label = "&#10003; success" if result.success else "&#10007; failed"
                detail = ""
                if not result.success and result.exception:
                    detail = f'<span class="mono">{_escape(str(result.exception))}</span>'
                elif result.success and result.return_value is not None:
                    detail = f'<span class="mono">{_escape(repr(result.return_value))}</span>'
                rows.append(
                    f"<tr>"
                    f'<td class="mono">{result.finished_at.strftime("%H:%M:%S.%f")[:-3]}</td>'
                    f"<td><strong>{_escape(result.job_name)}</strong></td>"
                    f'<td><span class="{result_cls}">{result_label}</span></td>'
                    f"<td>{_fmt_duration(result.started_at, result.finished_at)}</td>"
                    f"<td>{detail}</td>"
                    f"</tr>"
                )
            timeline_rows = "\n".join(rows)
        else:
            timeline_rows = _NO_EVENTS

        # ── Dependency graph ─────────────────────────────────────────
        dep_graph = _build_dep_graph(jobs)

        return _HTML_TEMPLATE.format(
            refreshed=datetime.now().strftime("%H:%M:%S"),
            job_count=len(jobs),
            event_count=len(all_results),
            jobs_rows=jobs_rows,
            timeline_rows=timeline_rows,
            dep_graph=_escape(dep_graph),
        )

    def log_message(self, fmt, *args):  # suppress default access log noise
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class DashboardServer:
    """
    Lightweight HTTP dashboard for a running Scheduler.

    Args:
        scheduler:  The :class:`~scheduler.Scheduler` instance to observe.
        host:       Interface to bind to (default ``"127.0.0.1"``).
        port:       Port to listen on (default ``8080``).

    The server runs in a daemon thread and is automatically cleaned up when
    the main process exits.  Call :meth:`stop` for an explicit shutdown.

    Example::

        dashboard = DashboardServer(scheduler, port=8080)
        dashboard.start()
        print(f"Dashboard: http://127.0.0.1:8080")
        # ...
        dashboard.stop()
    """

    def __init__(self, scheduler, host: str = "127.0.0.1", port: int = 8080) -> None:
        self._scheduler = scheduler
        self._host = host
        self._port = port
        self._httpd: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}"

    def start(self) -> "DashboardServer":
        """Start the dashboard HTTP server in a background daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return self

        # Build a handler class with the scheduler injected via class attribute
        scheduler_ref = self._scheduler

        class Handler(_DashboardHandler):
            scheduler = scheduler_ref

        self._httpd = HTTPServer((self._host, self._port), Handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="dashboard-server",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        """Shut down the HTTP server."""
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> "DashboardServer":
        return self.start()

    def __exit__(self, *_) -> None:
        self.stop()

    def __repr__(self) -> str:
        status = "running" if (self._thread and self._thread.is_alive()) else "stopped"
        return f"DashboardServer(url={self.url!r}, status={status!r})"
