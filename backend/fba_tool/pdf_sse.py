"""SSE 事件格式化与异步流式引擎（PDF 标签转换等流式任务）。"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import threading
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence, Tuple

from fba_tool.pdf_label_processor import (
    ProcessOptions,
    process_files_parallel,
    resolve_size_params,
)

logger = logging.getLogger(__name__)


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
    batch_id: str | None = None,
) -> str:
    payload_files = [
        {
            "filename": os.path.basename(name),
            "pdf_base64": base64.b64encode(data).decode("ascii"),
            "size_bytes": len(data),
        }
        for name, data in files
        if data
    ]
    payload: Dict[str, Any] = {
        "event": "complete",
        "progress": progress,
        "message": message or f"全部完成，共 {len(payload_files)} 个文件",
        "files": payload_files,
    }
    if batch_id:
        payload["batch_id"] = batch_id
        payload["download_url"] = f"/api/pdf/download_batch/{batch_id}"
    return sse_event(payload)


def sse_complete_batch(
    batch_id: str,
    file_count: int,
    total_bytes: int,
    *,
    progress: int = 100,
    message: str | None = None,
    files_meta: List[Dict[str, Any]] | None = None,
) -> str:
    """轻量完成事件（零 Base64），彻底避免巨型文件引发 OOM 内存爆炸。"""
    payload: Dict[str, Any] = {
        "event": "complete",
        "progress": progress,
        "message": message or f"全部完成，共 {file_count} 个文件",
        "batch_id": batch_id,
        "download_url": f"/api/pdf/download_batch/{batch_id}",
        "file_count": file_count,
        "total_bytes": total_bytes,
    }
    if files_meta:
        payload["files"] = files_meta
    return sse_event(payload)


def sse_error(message: str) -> str:
    return sse_event({"event": "error", "message": message})


class PdfBatchStore:
    """线程安全的内存临时交付仓库，提供 batch_id 流式下载，消除 SSE 巨型 Base64 膨胀。"""

    def __init__(self, ttl_seconds: int = 900, max_batches: int = 50):
        self._store: Dict[str, Tuple[float, List[Tuple[str, bytes]]]] = {}
        self._lock = threading.Lock()
        self.ttl_seconds = ttl_seconds
        self.max_batches = max_batches

    def _cleanup_unlocked(self, now: float) -> None:
        expired = [bid for bid, (created, _) in self._store.items() if now - created > self.ttl_seconds]
        for bid in expired:
            del self._store[bid]
        if len(self._store) > self.max_batches:
            oldest = sorted(self._store.keys(), key=lambda k: self._store[k][0])
            for bid in oldest[: len(self._store) - self.max_batches]:
                del self._store[bid]

    def put(self, files: List[Tuple[str, bytes]]) -> str:
        batch_id = uuid.uuid4().hex
        now = time.time()
        with self._lock:
            self._cleanup_unlocked(now)
            self._store[batch_id] = (now, files)
        return batch_id

    def get(self, batch_id: str) -> Optional[List[Tuple[str, bytes]]]:
        now = time.time()
        with self._lock:
            self._cleanup_unlocked(now)
            record = self._store.get(batch_id)
            if record:
                return record[1]
        return None

    def remove(self, batch_id: str) -> None:
        with self._lock:
            self._store.pop(batch_id, None)


BATCH_STORE = PdfBatchStore()


async def iter_convert_labels_sse(
    items: list[tuple[str, bytes]],
    size_key: str,
    width_mm: float | None,
    height_mm: float | None,
    *,
    options: ProcessOptions | None = None,
    request: Any = None,
    keepalive_interval: float = 4.0,
    include_base64: bool | None = None,
) -> AsyncIterator[str]:
    """原生异步生成器 (async def)：通过 asyncio.Queue 跨线程解耦，零占用 AnyIO 线程池。"""
    loop = asyncio.get_running_loop()
    event_queue: asyncio.Queue[str | None] = asyncio.Queue()
    cancel_event = threading.Event()

    def _safe_put(chunk: str | None) -> None:
        if cancel_event.is_set():
            return
        try:
            if not loop.is_closed():
                loop.call_soon_threadsafe(event_queue.put_nowait, chunk)
        except RuntimeError:
            pass

    def emit_progress(pct: int, msg: str) -> None:
        _safe_put(sse_progress(pct, msg))

    def worker() -> None:
        try:
            size = resolve_size_params(size_key, width_mm, height_mm)
            emit_progress(3, f"目标尺寸：{size.name}（{size.width_mm}×{size.height_mm} mm）")

            processed = process_files_parallel(
                items,
                size,
                options=options,
                on_progress=emit_progress,
                cancel_event=cancel_event,
            )
            if cancel_event.is_set():
                return

            if not processed:
                _safe_put(sse_error("未检测到可处理的 PDF 内容"))
                return

            emit_progress(98, "正在准备交付文件…")
            file_pairs = [(p.name, p.pdf_bytes) for p in processed]
            batch_id = BATCH_STORE.put(file_pairs)
            total_bytes = sum(len(b) for _, b in file_pairs)

            # 内存防爆判定：大于 5MB 或显式禁用 base64 时不灌装大文本，防止 OOM
            embed_b64 = include_base64 if include_base64 is not None else (total_bytes <= 5 * 1024 * 1024)

            if embed_b64:
                final_event = sse_complete_files(
                    file_pairs,
                    message=f"全部完成，正在准备下载 {len(processed)} 个文件…",
                    batch_id=batch_id,
                )
            else:
                files_meta = [
                    {"filename": os.path.basename(name), "size_bytes": len(data)}
                    for name, data in file_pairs
                ]
                final_event = sse_complete_batch(
                    batch_id=batch_id,
                    file_count=len(processed),
                    total_bytes=total_bytes,
                    message=f"全部完成，正在下载 {len(processed)} 个文件…",
                    files_meta=files_meta,
                )
            _safe_put(final_event)
        except Exception as exc:
            if not cancel_event.is_set():
                logger.exception("PDF label conversion worker error: %s", exc)
                _safe_put(sse_error(f"PDF 标签转换失败：{exc}"))
        finally:
            _safe_put(None)

    # 启动后台运算线程
    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()

    # 立即推送一条 processing 占位帧，防止反向代理网关超时
    yield ": processing\n\n"

    try:
        while True:
            # 监听客户端主动断开
            if request is not None and hasattr(request, "is_disconnected"):
                if await request.is_disconnected():
                    cancel_event.set()
                    logger.info("SSE client disconnected, aborted worker.")
                    break

            try:
                chunk = await asyncio.wait_for(event_queue.get(), timeout=keepalive_interval)
            except asyncio.TimeoutError:
                # 心跳包发射（3.0~5.0s 合理周期）
                yield ": keepalive\n\n"
                continue
            except asyncio.CancelledError:
                cancel_event.set()
                logger.info("SSE stream cancelled by ASGI server.")
                raise

            if chunk is None:
                break
            yield chunk
    finally:
        cancel_event.set()
