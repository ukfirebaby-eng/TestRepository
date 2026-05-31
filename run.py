import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import uvicorn


HOST = "127.0.0.1"
DEFAULT_PORT = 8000


# Load .env from the same directory as this script before anything else reads os.environ
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _listening_pids_for_port(port: int) -> list[int]:
    if os.name != "nt":
        return []

    try:
        completed = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return []

    pids: set[int] = set()
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP" or parts[3].upper() != "LISTENING":
            continue
        local_address = parts[1]
        if local_address.endswith(f":{port}"):
            try:
                pids.add(int(parts[4]))
            except ValueError:
                continue
    return sorted(pids)


def _pid_command_line(pid: int) -> str:
    if os.name != "nt":
        return ""

    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter \"ProcessId = {pid}\").CommandLine",
            ],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return ""
    return completed.stdout.strip()


def _pid_image_name(pid: int) -> str:
    if os.name != "nt":
        return ""

    try:
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return ""

    line = completed.stdout.strip().splitlines()
    if not line or "INFO:" in line[0]:
        return ""
    return line[0].split(",", 1)[0].strip().strip('"').lower()


def _stop_project_python_processes(pids: list[int], project_dir: Path) -> list[int]:
    stopped: list[int] = []
    project_marker = str(project_dir).lower()
    force_stop_port_process = _env_flag("DIAMOND_MINER_FORCE_STOP_PORT_PROCESS")

    for pid in pids:
        if pid == os.getpid():
            continue
        command_line = _pid_command_line(pid).lower()
        image_name = _pid_image_name(pid)
        is_project_python = "python" in command_line and project_marker in command_line
        is_python_on_port_with_unreadable_command = not command_line and image_name in {"python.exe", "pythonw.exe"}
        if not (is_project_python or is_python_on_port_with_unreadable_command or force_stop_port_process):
            continue
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, check=False)
            stopped.append(pid)
        except OSError:
            continue
    return stopped


def ensure_port_available(host: str, port: int, project_dir: Path) -> None:
    if not _is_port_open(host, port):
        return

    pids = _listening_pids_for_port(port)
    if _env_flag("DIAMOND_MINER_STOP_STALE_SERVER"):
        stopped = _stop_project_python_processes(pids, project_dir)
        if stopped:
            for _ in range(20):
                if not _is_port_open(host, port, timeout=0.2):
                    return
                time.sleep(0.2)

    pid_hint = f" PID(s): {', '.join(str(pid) for pid in pids)}." if pids else ""
    raise RuntimeError(
        f"Port {port} is already in use on {host}.{pid_hint} "
        "Stop the stale server process, choose DIAMOND_MINER_PORT, or set "
        "DIAMOND_MINER_STOP_STALE_SERVER=1 to stop Python processes bound to this port. "
        "If Windows blocks process inspection, also set DIAMOND_MINER_FORCE_STOP_PORT_PROCESS=1."
    )


def validate_directories() -> None:
    print("[*] Checking physical directory structures...")
    required_dirs = ["./vaults", "./static", "./temp_uploads"]
    for directory in required_dirs:
        os.makedirs(directory, exist_ok=True)
        print(f"    -> Validated: {directory}/")


def print_llm_config() -> None:
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    if provider == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY", "")
        key_display = f"{key[:8]}..." if len(key) > 8 else "(not set)"
        fast = os.environ.get("FAST_MODEL", "openai/gpt-4o-mini")
        smart = os.environ.get("SMART_MODEL", "openai/gpt-4o")
        print(f"[*] LLM Provider: OpenRouter  |  Key: {key_display}")
    else:
        key = os.environ.get("OPENAI_API_KEY", "")
        key_display = f"{key[:8]}..." if len(key) > 8 else "(not set)"
        fast = os.environ.get("FAST_MODEL", "gpt-4o-mini")
        smart = os.environ.get("SMART_MODEL", "gpt-4o")
        print(f"[*] LLM Provider: OpenAI     |  Key: {key_display}")
    print(f"    -> Fast model:  {fast}")
    print(f"    -> Smart model: {smart}")


def main() -> int:
    print("""
    =========================================
    DIAMOND MINER AI ENGINE INITIALIZING
    =========================================
    """)

    validate_directories()
    print_llm_config()

    port = int(os.environ.get("DIAMOND_MINER_PORT", str(DEFAULT_PORT)))
    try:
        ensure_port_available(HOST, port, Path(__file__).parent.resolve())
    except RuntimeError as exc:
        print(f"\n[!] {exc}", file=sys.stderr)
        return 1

    print("\n[*] Boot sequence complete. Starting Uvicorn ASGI server...")
    print(f"[*] Spatial Canvas UI will be available at: http://localhost:{port}\n")

    uvicorn.run("api:app", host=HOST, port=port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
