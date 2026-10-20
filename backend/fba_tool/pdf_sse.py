"""SSE 事件格式化（PDF 转换等流式任务）。"""
from __future__ import annotations

import base64
import json
import os
import threading
from queue import Empty, Queue
from typing import Any, Dict, Iterator, List, Sequence, Tuple

from fba_tool.pdf_label_processor import ProcessOptions, process_files_parallel, resolve_size_params


def pdf_download_filename(size, prefix: str = "标签转换") -> str:
    if size.key == "carton_100x100":
        return "10x10热敏箱贴.pdf"
    if size.key == "custom":
        return f"{prefix}_{size.width_mm}x{size.height_mm}mm.pdf"
    return f"{prefix}_{size.name.replace('×', 'x').replace(' ', '')}.pdf"


def sse_event(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sse_progress(progress: int, message: str, **extra: Any) -> str:
    body: Dict[str, Any] = {"progress": progress, "message": message}
    body.update(extra)
    return sse_event(body)


def sse_complete_files(
    files: Sequence[Tuple[str, bytes]],
    *,
    progress: int = 100,
    message: str | None = None,
) -> str:
    payload_files = [
        {
            "filename": os.path.basename(name),
            "pdf_base64": base64.b64encode(data).decode("ascii"),
        }
        for name, data in files
        if data
    ]
    return sse_event(
        {
            "event": "complete",
            "progress": progress,
            "message": message or f"全部完成，共 {len(payload_files)} 个文件",
            "files": payload_files,
        }
    )


def sse_error(message: str) -> str:
    return sse_event({"event": "error", "message": message})


def iter_convert_labels_sse(
    items: list[tuple[str, bytes]],
    size_key: str,
    width_mm: float | None,
    height_mm: float | None,
    *,
    options: ProcessOptions | None = None,
) -> Iterator[str]:
    """在后台线程并行处理 PDF，通过队列实时 yield SSE 事件。"""
    event_queue: Queue[str | None] = Queue()

    def emit_progress(pct: int, msg: str) -> None:
        event_queue.put(sse_progress(pct, msg))

    def worker() -> None:
        try:
            size = resolve_size_params(size_key, width_mm, height_mm)
            emit_progress(3, f"目标尺寸：{size.name}（{size.width_mm}×{size.height_mm} mm）")

            processed = process_files_parallel(items, size, options=options, on_progress=emit_progress)
            if not processed:
                event_queue.put(sse_error("未检测到可处理的 PDF 内容"))
                return

            emit_progress(98, "正在准备下载文件…")
            event_queue.put(
                sse_complete_files(
                    [(p.name, p.pdf_bytes) for p in processed],
                    message=f"全部完成，正在下载 {len(processed)} 个文件…",
                )
            )
        except Exception as exc:
            event_queue.put(sse_error(f"PDF 标签转换失败：{exc}"))
        finally:
            event_queue.put(None)

    event_queue.put(sse_progress(1, f"已接收 {len(items)} 个文件，准备并行处理…"))
    threading.Thread(target=worker, daemon=True).start()

    # 立即推送一条 keepalive，避免代理/浏览器在首个检测完成前长时间无响应体
    yield ": processing\n\n"

    while True:
        try:
            chunk = event_queue.get(timeout=0.25)
        except Empty:
            yield ": keepalive\n\n"
            continue
        if chunk is None:
            break
        yield chunk
