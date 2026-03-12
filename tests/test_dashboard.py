"""Tests for the unified story dashboard."""

import time
import unittest
import urllib.request
from datetime import datetime, timedelta

from scheduler import Job, Scheduler
from scheduler.schedules import IntervalSchedule, OneTimeSchedule
from dashboard import DashboardServer


def _free_port() -> int:
    """Return an available TCP port."""
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestDashboardServer(unittest.TestCase):

    def setUp(self):
        self.scheduler = Scheduler(tick_interval=0.05)
        self.port = _free_port()
        self.dashboard = DashboardServer(
            self.scheduler, host="127.0.0.1", port=self.port
        )

    def tearDown(self):
        self.dashboard.stop()
        self.scheduler.stop(wait=False)

    # ------------------------------------------------------------------

    def test_start_stop(self):
        self.dashboard.start()
        self.assertIn("running", repr(self.dashboard))
        self.dashboard.stop()
        self.assertIn("stopped", repr(self.dashboard))

    def test_url_property(self):
        self.assertEqual(self.dashboard.url, f"http://127.0.0.1:{self.port}")

    def test_html_response(self):
        self.dashboard.start()
        time.sleep(0.1)
        with urllib.request.urlopen(self.dashboard.url) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
        self.assertIn("Job Scheduler", body)
        self.assertIn("Unified Story Dashboard", body)

    def test_html_shows_jobs(self):
        self.scheduler.add_job(Job(
            "test_job",
            lambda: None,
            IntervalSchedule(seconds=60),
        ))
        self.dashboard.start()
        time.sleep(0.1)
        with urllib.request.urlopen(self.dashboard.url) as resp:
            body = resp.read().decode("utf-8")
        self.assertIn("test_job", body)
        self.assertIn("pending", body)

    def test_json_api(self):
        import json
        self.scheduler.add_job(Job(
            "api_job",
            lambda: 42,
            IntervalSchedule(seconds=60),
        ))
        self.dashboard.start()
        time.sleep(0.1)
        url = f"http://127.0.0.1:{self.port}/api/jobs"
        with urllib.request.urlopen(url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(len(data), 1)
        job_data = data[0]
        self.assertEqual(job_data["name"], "api_job")
        self.assertEqual(job_data["status"], "pending")
        self.assertEqual(job_data["run_count"], 0)
        self.assertEqual(job_data["dependencies"], [])

    def test_json_api_shows_dependencies(self):
        import json
        self.scheduler.add_job(Job("root_job", lambda: None, IntervalSchedule(seconds=60)))
        self.scheduler.add_job(Job(
            "child_job", lambda: None, IntervalSchedule(seconds=60),
            dependencies=["root_job"],
        ))
        self.dashboard.start()
        time.sleep(0.1)
        url = f"http://127.0.0.1:{self.port}/api/jobs"
        with urllib.request.urlopen(url) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        by_name = {d["name"]: d for d in data}
        self.assertEqual(by_name["child_job"]["dependencies"], ["root_job"])
        self.assertEqual(by_name["root_job"]["dependencies"], [])

    def test_timeline_shows_executions(self):
        executed = []

        def fast_job():
            executed.append(True)

        self.scheduler.add_job(Job(
            "fast_job",
            fast_job,
            OneTimeSchedule(datetime.now() + timedelta(milliseconds=50)),
        ))
        self.scheduler.start()
        self.dashboard.start()
        time.sleep(0.5)

        with urllib.request.urlopen(self.dashboard.url) as resp:
            body = resp.read().decode("utf-8")
        # The timeline should mention the job
        self.assertIn("fast_job", body)
        # At least one execution should have happened
        self.assertGreater(len(executed), 0)

    def test_404_for_unknown_path(self):
        self.dashboard.start()
        time.sleep(0.1)
        url = f"http://127.0.0.1:{self.port}/does-not-exist"
        try:
            urllib.request.urlopen(url)
            self.fail("Expected HTTPError 404")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 404)

    def test_context_manager(self):
        with DashboardServer(self.scheduler, host="127.0.0.1", port=_free_port()) as dash:
            time.sleep(0.1)
            with urllib.request.urlopen(dash.url) as resp:
                self.assertEqual(resp.status, 200)

    def test_idempotent_start(self):
        """Calling start() twice should not raise or spawn extra threads."""
        self.dashboard.start()
        thread_before = self.dashboard._thread
        self.dashboard.start()
        self.assertIs(self.dashboard._thread, thread_before)

    def test_no_jobs_renders_without_error(self):
        """Dashboard should render gracefully when no jobs are registered."""
        self.dashboard.start()
        time.sleep(0.1)
        with urllib.request.urlopen(self.dashboard.url) as resp:
            body = resp.read().decode("utf-8")
        self.assertIn("No jobs registered", body)
        self.assertIn("No executions yet", body)


if __name__ == "__main__":
    unittest.main()
