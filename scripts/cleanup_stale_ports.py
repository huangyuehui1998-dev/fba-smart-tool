"""启动前清理僵死后端：端口仍在 LISTENING 但 /api/health 超时或无响应。"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable


def _parse_ports_file(path: Path) -> set[int]:
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    ports: set[int] = set()
    for key in ("backend", "frontend"):
        val = data.get(key)
        if isinstance(val, int) and val > 0:
            ports.add(val)
    return ports


def _candidate_ports(start: int, end: int, extra: Iterable[int]) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for port in sorted(extra):
        if start <= port <= end and port not in seen:
            seen.add(port)
            ordered.append(port)
    for port in range(start, end + 1):
        if port not in seen:
            seen.add(port)
            ordered.append(port)
    return ordered


def _listening_pids(host: str, port: int) -> list[int]:
    system = platform.system()
    pids: set[int] = set()
    port_text = str(port)

    if system == "Windows":
        try:
            out = subprocess.check_output(
                ["netstat", "-ano", "-p", "tcp"],
                text=True,
                errors="replace",
            )
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

    if system in {"Linux", "Darwin"}:
        try:
            out = subprocess.check_output(["ss", "-ltnp"], text=True, errors="replace")
        except (OSError, subprocess.CalledProcessError):
            try:
                out = subprocess.check_output(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], text=True)
            except (OSError, subprocess.CalledProcessError):
                return []
            for line in out.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    pids.add(int(parts[1]))
            return sorted(pids)
        needle = f":{port_text}"
        for line in out.splitlines():
            if "LISTEN" not in line or needle not in line:
                continue
            if "pid=" in line:
                for chunk in line.split(","):
                    chunk = chunk.strip()
                    if chunk.startswith("pid="):
                        pid_text = chunk[4:]
                        if pid_text.isdigit():
                            pids.add(int(pid_text))
        return sorted(pids)

    return []


def _health_ok(host: str, port: int, timeout: float) -> bool:
    url = f"http://{host}:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return False
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            return data.get("status") == "ok"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return False


def _kill_pid(pid: int) -> bool:
    if pid <= 0:
        return False
    system = platform.system()
    try:
        if system == "Windows":
            proc = subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                text=True,
            )
            return proc.returncode == 0
        proc = subprocess.run(["kill", "-9", str(pid)], capture_output=True, text=True)
        return proc.returncode == 0
    except OSError:
        return False


def cleanup_stale_ports(
    *,
    host: str = "127.0.0.1",
    start: int = 8000,
    end: int = 8099,
    ports_file: Path | None = None,
    timeout: float = 2.5,
    dry_run: bool = False,
) -> int:
    extra = _parse_ports_file(ports_file) if ports_file else set()
    killed = 0
    checked = 0

    for port in _candidate_ports(start, end, extra):
        pids = _listening_pids(host, port)
        if not pids:
            continue
        checked += 1
        if _health_ok(host, port, timeout):
            print(f"[cleanup] port {port} healthy (PID {', '.join(map(str, pids))}), keep")
            continue
        print(f"[cleanup] port {port} stale (PID {', '.join(map(str, pids))}), removing…")
        for pid in pids:
            if dry_run:
                print(f"[cleanup]   [dry-run] would kill PID {pid}")
                killed += 1
            elif _kill_pid(pid):
                killed += 1
                print(f"[cleanup]   killed PID {pid}")
            else:
                print(f"[cleanup]   failed to kill PID {pid}", file=sys.stderr)

    if checked == 0:
        print(f"[cleanup] no listeners on {host}:{start}-{end}")
    else:
        print(f"[cleanup] done: checked {checked} listener(s), killed {killed} process(es)")
    return 0 if killed >= 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Kill stale FBA backend listeners before dev startup")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--start", type=int, default=8000)
    parser.add_argument("--end", type=int, default=8099)
    parser.add_argument("--ports-file", type=Path, default=None)
    parser.add_argument("--timeout", type=float, default=2.5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    raise SystemExit(
        cleanup_stale_ports(
            host=args.host,
            start=args.start,
            end=args.end,
            ports_file=args.ports_file,
            timeout=args.timeout,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
