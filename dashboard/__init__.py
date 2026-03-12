"""
Unified Story Dashboard for the Job Scheduler.

Provides a live HTTP dashboard showing job statuses, execution history,
and a unified timeline ("story") of scheduler activity.

Usage::

    from scheduler import Scheduler
    from dashboard import DashboardServer

    scheduler = Scheduler()
    # ... add jobs ...
    scheduler.start()

    dashboard = DashboardServer(scheduler, host="127.0.0.1", port=8080)
    dashboard.start()
    # Open http://127.0.0.1:8080 in a browser
    # ...
    dashboard.stop()
"""

from .server import DashboardServer

__all__ = ["DashboardServer"]
