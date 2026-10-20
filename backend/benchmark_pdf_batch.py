"""PDF 标签批量压测：直接打后端 API，不经过 Vite 代理。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIRS = [
    ROOT / "app_data" / "templates",
    ROOT / "dist" / "app_data" / "templates",
    ROOT / "backend" / "templates",
]


def find_template_pdfs() -> list[Path]:
    for d in TEMPLATE_DIRS:
        if not d.is_dir():
            continue
        pdfs = sorted(d.glob("*.pdf"))
        if pdfs:
            return pdfs
    raise FileNotFoundError(f"未找到 PDF 模板，已检查：{', '.join(str(p) for p in TEMPLATE_DIRS)}")


def build_multipart(files: list[tuple[str, bytes]], fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = "----FbaPdfBenchBoundary"
    parts: list[bytes] = []
    for name, data in files:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
            f"Content-Type: application/pdf\r\n\r\n".encode()
            + data
            + b"\r\n"
        )
    for key, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
        )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    return body, boundary


def run_stream_benchmark(
    base_url: str,
    pdf_paths: list[Path],
    detect_dpi: int,
) -> dict:
    files = [(p.name, p.read_bytes()) for p in pdf_paths]
    body, boundary = build_multipart(
        files,
        {
            "size_key": "carton_100x100",
            "padding_mm": "1.0",
            "detect_dpi": str(detect_dpi),
        },
    )
    url = f"{base_url.rstrip('/')}/api/pdf/convert_labels/stream"
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Accept", "text/event-stream")

    t0 = time.perf_counter()
    first_event_at: float | None = None
    last_progress = -1
    last_message = ""
    complete = False
    error = ""
    events = 0

    with urllib.request.urlopen(req, timeout=600) as resp:
        buf = b""
        while True:
            chunk = resp.read(8192)
            if not chunk:
                break
            buf += chunk
            while b"\n\n" in buf:
                block, buf = buf.split(b"\n\n", 1)
                text = block.decode("utf-8", errors="replace")
                if not text.strip() or text.startswith(":"):
                    continue
                for line in text.split("\n"):
                    if not line.startswith("data: "):
                        continue
                    events += 1
                    if first_event_at is None:
                        first_event_at = time.perf_counter()
                    payload = json.loads(line[6:])
                    if payload.get("event") == "error":
                        error = str(payload.get("message") or "unknown error")
                    if payload.get("event") == "complete":
                        complete = True
                    if payload.get("progress") is not None:
                        last_progress = int(payload["progress"])
                    if payload.get("message"):
                        last_message = str(payload["message"])

    elapsed = time.perf_counter() - t0
    return {
        "file_count": len(pdf_paths),
        "detect_dpi": detect_dpi,
        "events": events,
        "first_event_s": None if first_event_at is None else round(first_event_at - t0, 2),
        "elapsed_s": round(elapsed, 2),
        "last_progress": last_progress,
        "last_message": last_message,
        "complete": complete,
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PDF label batch benchmark")
    parser.add_argument("--base-url", default="http://127.0.0.1:8012")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--dpis", default="120,200,300")
    args = parser.parse_args()

    sources = find_template_pdfs()
    print(f"模板 PDF：{len(sources)} 个，来源 {sources[0].parent}")

    # 健康检查
    health_url = f"{args.base_url.rstrip('/')}/api/health"
    try:
        with urllib.request.urlopen(health_url, timeout=5) as resp:
            print(f"后端健康：{resp.read().decode().strip()}")
    except Exception as exc:
        print(f"[FAIL] 后端不可达 {health_url}：{exc}", file=sys.stderr)
        return 1

    dpis = [int(x.strip()) for x in args.dpis.split(",") if x.strip()]
    batch: list[Path] = []
    while len(batch) < args.count:
        batch.extend(sources)
    batch = batch[: args.count]

    print(f"\n压测规模：{len(batch)} 个 PDF\n{'=' * 60}")
    failed = 0
    for dpi in dpis:
        print(f"\n[DPI {dpi}] 开始…")
        try:
            result = run_stream_benchmark(args.base_url, batch, dpi)
            status = "OK" if result["complete"] and not result["error"] else "FAIL"
            print(
                f"  {status} | 首事件 {result['first_event_s']}s | "
                f"总耗时 {result['elapsed_s']}s | 进度 {result['last_progress']}% | "
                f"SSE事件 {result['events']} 条"
            )
            print(f"  末条消息：{result['last_message']}")
            if result["error"]:
                print(f"  错误：{result['error']}")
                failed += 1
        except Exception as exc:
            print(f"  FAIL | {exc}")
            failed += 1

    print(f"\n{'=' * 60}")
    if failed:
        print(f"完成：{len(dpis) - failed}/{len(dpis)} 通过")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
