from pathlib import Path
from unittest.mock import Mock

import pytest

import run as app_runner


def test_ensure_port_available_returns_when_port_is_free(monkeypatch, tmp_path):
    monkeypatch.setattr(app_runner, "_is_port_open", lambda host, port, timeout=0.5: False)

    app_runner.ensure_port_available("127.0.0.1", 8000, tmp_path)


def test_ensure_port_available_reports_occupied_port_without_auto_stop(monkeypatch, tmp_path):
    monkeypatch.setattr(app_runner, "_is_port_open", lambda host, port, timeout=0.5: True)
    monkeypatch.setattr(app_runner, "_listening_pids_for_port", lambda port: [1234])

    with pytest.raises(RuntimeError, match="Port 8000 is already in use"):
        app_runner.ensure_port_available("127.0.0.1", 8000, tmp_path)


def test_ensure_port_available_can_stop_stale_project_python_process(monkeypatch, tmp_path):
    checks = iter([True, False])
    stop = Mock(return_value=[1234])
    monkeypatch.setenv("DIAMOND_MINER_STOP_STALE_SERVER", "1")
    monkeypatch.setattr(app_runner, "_is_port_open", lambda host, port, timeout=0.5: next(checks))
    monkeypatch.setattr(app_runner, "_listening_pids_for_port", lambda port: [1234])
    monkeypatch.setattr(app_runner, "_stop_project_python_processes", stop)

    app_runner.ensure_port_available("127.0.0.1", 8000, Path(tmp_path))

    stop.assert_called_once_with([1234], Path(tmp_path))


def test_stop_project_python_processes_allows_unreadable_python_bound_to_port(monkeypatch, tmp_path):
    killed = []
    monkeypatch.setattr(app_runner, "_pid_command_line", lambda pid: "")
    monkeypatch.setattr(app_runner, "_pid_image_name", lambda pid: "python.exe")
    monkeypatch.setattr(app_runner.subprocess, "run", lambda args, capture_output, check: killed.append(args))

    stopped = app_runner._stop_project_python_processes([1234], tmp_path)

    assert stopped == [1234]
    assert killed == [["taskkill", "/PID", "1234", "/F"]]


def test_stop_project_python_processes_requires_force_for_uninspectable_non_python(monkeypatch, tmp_path):
    killed = []
    monkeypatch.setattr(app_runner, "_pid_command_line", lambda pid: "")
    monkeypatch.setattr(app_runner, "_pid_image_name", lambda pid: "")
    monkeypatch.setattr(app_runner.subprocess, "run", lambda args, capture_output, check: killed.append(args))

    stopped = app_runner._stop_project_python_processes([1234], tmp_path)

    assert stopped == []
    assert killed == []


def test_stop_project_python_processes_force_stops_uninspectable_port_process(monkeypatch, tmp_path):
    killed = []
    monkeypatch.setenv("DIAMOND_MINER_FORCE_STOP_PORT_PROCESS", "1")
    monkeypatch.setattr(app_runner, "_pid_command_line", lambda pid: "")
    monkeypatch.setattr(app_runner, "_pid_image_name", lambda pid: "")
    monkeypatch.setattr(app_runner.subprocess, "run", lambda args, capture_output, check: killed.append(args))

    stopped = app_runner._stop_project_python_processes([1234], tmp_path)

    assert stopped == [1234]
    assert killed == [["taskkill", "/PID", "1234", "/F"]]
