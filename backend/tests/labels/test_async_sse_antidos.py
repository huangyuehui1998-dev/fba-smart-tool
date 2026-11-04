"""针对原生异步 SSE 生成器、防 DoS 与大文件低内存交付的专项自动化测试。"""
from __future__ import annotations

import asyncio
import io
import os
import zipfile
import fitz
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from fba_tool.pdf_label_processor import (
    MAX_PHYSICAL_PAGE_PT,
    MAX_RASTER_DIM_PX,
    PDFLabelProcessor,
    ProcessOptions,
    mm_to_pt,
)
from fba_tool.pdf_sse import (
    BATCH_STORE,
    iter_convert_labels_sse,
    sse_complete_batch,
    sse_complete_files,
    sse_error,
    sse_progress,
)
from main import app
from routers.pdf_tools import MAX_DOC_PAGES, _ensure_pdf


def _create_sample_pdf(pages: int = 1, width_pt: float = 283.46, height_pt: float = 283.46) -> bytes:
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=width_pt, height=height_pt)
        page.draw_rect(fitz.Rect(20, 20, width_pt - 20, height_pt - 20), color=(0, 0, 0), width=2)
        page.insert_text((40, 50), "TEST LABEL FBA123456", fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def test_ensure_pdf_rejects_encrypted_doc():
    doc = fitz.open()
    doc.new_page(width=100, height=100)
    perm = int(
        fitz.PDF_PERM_ACCESSIBILITY
        | fitz.PDF_PERM_PRINT
        | fitz.PDF_PERM_COPY
        | fitz.PDF_PERM_ANNOTATE
    )
    enc_bytes = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="password123",
        owner_pw="owner123",
        permissions=perm,
    )
    doc.close()

    with pytest.raises(HTTPException) as exc_info:
        _ensure_pdf("secret.pdf", enc_bytes)
    assert exc_info.value.status_code == 400
    assert "加密" in exc_info.value.detail or "密码" in exc_info.value.detail


def test_ensure_pdf_rejects_over_100_pages():
    huge_pdf = _create_sample_pdf(pages=MAX_DOC_PAGES + 1)
    with pytest.raises(HTTPException) as exc_info:
        _ensure_pdf("bomb_101.pdf", huge_pdf)
    assert exc_info.value.status_code == 400
    assert f"超过系统限制（最大 {MAX_DOC_PAGES} 页）" in exc_info.value.detail


def test_dynamic_downsampling_on_huge_physical_dimensions():
    # 尺寸达到 3000 pt x 3000 pt（远超 1700 pt 上限）
    huge_dim_pdf = _create_sample_pdf(pages=1, width_pt=3000, height_pt=3000)
    doc = fitz.open(stream=huge_dim_pdf, filetype="pdf")
    page = doc[0]

    proc = PDFLabelProcessor(ProcessOptions(detect_dpi=300))
    scale = proc.opt.detect_dpi / 72.0
    max_pt = max(page.rect.width, page.rect.height)
    assert max_pt > MAX_PHYSICAL_PAGE_PT

    # 执行检测，内部会自动降采样，光栅化像素严格受控在 MAX_RASTER_DIM_PX 以内
    boxes = proc._detect_page_labels(page, 0)
    assert isinstance(boxes, list)

    effective_scale = min(scale, MAX_RASTER_DIM_PX / max_pt)
    assert (max_pt * effective_scale) <= MAX_RASTER_DIM_PX
    doc.close()


@pytest.mark.anyio
async def test_iter_convert_labels_sse_async_stream():
    pdf_bytes = _create_sample_pdf(pages=1)
    items = [("shipment_1.pdf", pdf_bytes)]

    chunks = []
    async for chunk in iter_convert_labels_sse(items, "carton_100x100", None, None):
        chunks.append(chunk)

    assert len(chunks) >= 3
    assert chunks[0] == ": processing\n\n"
    all_text = "".join(chunks)
    assert "data: " in all_text
    assert '"event": "complete"' in all_text
    assert "batch_id" in all_text


@pytest.mark.anyio
async def test_iter_convert_labels_sse_client_disconnect():
    pdf_bytes = _create_sample_pdf(pages=1)
    items = [("shipment_1.pdf", pdf_bytes)]

    class MockDisconnectRequest:
        def __init__(self):
            self.calls = 0

        async def is_disconnected(self):
            self.calls += 1
            return self.calls > 1

    chunks = []
    async for chunk in iter_convert_labels_sse(
        items,
        "carton_100x100",
        None,
        None,
        request=MockDisconnectRequest(),
    ):
        chunks.append(chunk)

    # 断开后迅速退出，不会无限期挂起
    assert len(chunks) >= 1
    assert chunks[0] == ": processing\n\n"


def test_batch_store_and_download_endpoints():
    client = TestClient(app)
    pdf1 = _create_sample_pdf(pages=1)
    pdf2 = _create_sample_pdf(pages=1)

    # 1. 单文件批次
    bid1 = BATCH_STORE.put([("single.pdf", pdf1)])
    res1 = client.get(f"/api/pdf/download_batch/{bid1}")
    assert res1.status_code == 200
    assert res1.headers["content-type"] == "application/pdf"
    assert "single.pdf" in res1.headers.get("content-disposition", "")

    # 2. 多文件打包 ZIP 批次
    bid2 = BATCH_STORE.put([("f1.pdf", pdf1), ("f2.pdf", pdf2)])
    res2 = client.get(f"/api/pdf/download_batch/{bid2}")
    assert res2.status_code == 200
    assert "zip" in res2.headers["content-type"]
    zf = zipfile.ZipFile(io.BytesIO(res2.content))
    assert set(zf.namelist()) == {"f1.pdf", "f2.pdf"}

    # 3. 不存在的 batch_id
    res_404 = client.get("/api/pdf/download_batch/non_existent_batch_id")
    assert res_404.status_code == 404


def test_api_convert_labels_stream_headers():
    client = TestClient(app)
    pdf = _create_sample_pdf(pages=1)
    files = [("files", ("test.pdf", pdf, "application/pdf"))]
    resp = client.post("/api/pdf/convert_labels/stream", files=files, data={"size_key": "carton_100x100"})

    assert resp.status_code == 200
    assert resp.headers["X-Accel-Buffering"] == "no"
    assert "no-cache" in resp.headers["Cache-Control"]
    assert "text/event-stream" in resp.headers["content-type"]
    assert ": processing" in resp.text
    assert "complete" in resp.text
