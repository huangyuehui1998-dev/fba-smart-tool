"""Stop this project's recorded frontend/backend listeners (ports.json only)."""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTS_FILE = ROOT / ".dev" / "ports.json"
MARKERS = (
    "uvicorn",
    "vite",
    "FBA_Smart_Tool",
    "FBA Backend",
    "npm run dev",
    str(ROOT),
)


def _ports_from_file(path: Path) -> list[int]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    ports: list[int] = []
    for key in ("backend", "frontend"):
        val = data.get(key)
        if isinstance(val, int) and val > 0:
            ports.append(val)
    return ports


def _listening_pids(host: str, port: int) -> list[int]:
    pids: set[int] = set()
    port_text = str(port)
    if platform.system() != "Windows":
        try:
            out = subprocess.check_output(
                ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
                text=True,
                errors="replace",
            )
        except (OSError, subprocess.CalledProcessError):
            return []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                pids.add(int(parts[1]))
        return sorted(pids)

    try:
        out = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True, errors="replace")
    except (OSError, subprocess.CalledProcessError):
        return []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[3] != "LISTENING":
            continue
        local = parts[1]
        if local.rsplit(":", 1)[-1] != port_text:
            continue
        local_host = local.rsplit(":", 1)[0]
        if local_host not in {host, "0.0.0.0", "[::]", "[::1]", "*"}:
            continue
        pid_text = parts[-1]
        if pid_text.isdigit() and int(pid_text) > 0:
            pids.add(int(pid_text))
    return sorted(pids)


def _cmdline(pid: int) -> str:
    if platform.system() != "Windows":
        try:
            return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            return ""
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine",
            ],
            text=True,
            errors="replace",
            timeout=8,
        )
        return (out or "").strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""


def _is_this_app(cmdline: str) -> bool:
    text = cmdline.lower()
    if not text:
        return False
    return any(marker.lower() in text for marker in MARKERS)


def _kill(pid: int) -> bool:
    if platform.system() == "Windows":
        proc = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
        return proc.returncode == 0
    proc = subprocess.run(["kill", str(pid)], capture_output=True, text=True)
    return proc.returncode == 0


def stop_dev(host: str = "127.0.0.1", ports_file: Path | None = None, dry_run: bool = False) -> int:
    path = ports_file or PORTS_FILE
    ports = _ports_from_file(path)
    if not ports:
        print("[stop] no ports in", path)
        return 0
    killed = 0
    for port in ports:
        for pid in _listening_pids(host, port):
            cmd = _cmdline(pid)
            if not _is_this_app(cmd):
                print(f"[stop] skip PID {pid} on :{port} (not this app)")
                continue
            print(f"[stop] {'would kill' if dry_run else 'killing'} PID {pid} on :{port}")
            if not dry_run and _kill(pid):
                killed += 1
    print(f"[stop] done, killed {killed}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Stop FBA Smart Tool dev frontend/backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--ports-file", type=Path, default=PORTS_FILE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    raise SystemExit(stop_dev(host=args.host, ports_file=args.ports_file, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
