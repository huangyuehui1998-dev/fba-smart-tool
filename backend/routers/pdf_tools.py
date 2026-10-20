"""PDF 标签智能裁剪转换 — Step4 热敏箱贴 + 侧边栏通用工具。"""
from __future__ import annotations

import base64
import io
import os
import zipfile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from fba_tool.pdf_label_processor import (
    ProcessOptions,
    list_preset_sizes,
    parse_process_options,
    process_files_parallel,
    resolve_size_params,
    thermal_labels_pdf,
)
from fba_tool.pdf_sse import iter_convert_labels_sse, pdf_download_filename
from utils.responses import file_response, pdf_response

router = APIRouter()


MM_MIN, MM_MAX = 10.0, 600.0  # S8 D7：标签尺寸合理范围（热敏 10 mm 起，最大 A2 短边约 420 mm，留余量到 600）


def _parse_mm(value: Optional[str]) -> Optional[float]:
    """空 = 用预设尺寸；填了就必须是 10–600 之间的数字，否则 400（以前 -5、abc、100000 都被悄悄忽略或照做）。"""
    if value is None or str(value).strip() == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"尺寸「{value}」不是数字，请填毫米数（{MM_MIN:g}–{MM_MAX:g}）")
    if not (MM_MIN <= n <= MM_MAX):
        raise HTTPException(status_code=400, detail=f"尺寸 {value} mm 超出范围，请填 {MM_MIN:g}–{MM_MAX:g} mm")
    return n


def _ensure_pdf(name: str, raw: bytes) -> None:
    """S8 D7：坏 PDF / 冒充 PDF 的文件返回 400 并写明是哪个文件，不再 500。"""
    head = raw[:1024].lstrip()
    if not head.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail=f"{name} 不是 PDF 文件（文件头不是 %PDF），请上传亚马逊下载的箱唛 PDF")
    try:
        import fitz  # PyMuPDF

        with fitz.open(stream=raw, filetype="pdf") as doc:
            if doc.page_count < 1:
                raise ValueError("没有页面")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{name} 已损坏，打不开（{exc}）") from exc


def _decode_pdf_b64(b64: str, idx: int) -> bytes:
    import binascii

    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"第 {idx} 份 PDF 的 base64 数据损坏，无法解码") from exc
    _ensure_pdf(f"第 {idx} 份 PDF", raw)
    return raw


def _options_from_json_body(body: Dict[str, Any]) -> ProcessOptions:
    nested = body.get("options")
    if isinstance(nested, dict):
        return parse_process_options(nested)
    return parse_process_options(body)


def _options_from_form(
    padding_mm: Optional[str] = None,
    ignore_top_mm: Optional[str] = None,
    ignore_bottom_mm: Optional[str] = None,
    detect_dpi: Optional[str] = None,
    custom_text: Optional[str] = None,
) -> ProcessOptions:
    return parse_process_options(
        padding_mm=padding_mm,
        ignore_top_mm=ignore_top_mm,
        ignore_bottom_mm=ignore_bottom_mm,
        detect_dpi=detect_dpi,
        custom_text=custom_text,
    )


def _pdf_filename(size, prefix: str = "标签转换") -> str:
    return pdf_download_filename(size, prefix)


async def _read_pdf_uploads(files: List[UploadFile]) -> List[tuple[str, bytes]]:
    items: List[tuple[str, bytes]] = []
    for f in files:
        raw = await f.read()
        if raw:
            _ensure_pdf(f.filename or "upload.pdf", raw)
            items.append((f.filename or "upload.pdf", raw))
    return items


@router.get("/api/pdf/sizes")
def api_pdf_sizes():
    """返回可选目标尺寸列表（前端下拉菜单）。"""
    return {"sizes": list_preset_sizes()}


@router.post("/api/pdf/thermal_labels")
def api_thermal_labels(body: Dict[str, Any]):
    """模块 A：复用 Step4 校验返回的 pdf_base64 列表，生成热敏标签 PDF。"""
    b64_list: List[str] = body.get("pdf_base64") or []
    if not b64_list:
        shipments = body.get("shipments") or []
        b64_list = [str(s.get("pdf_base64") or "") for s in shipments if s.get("pdf_base64")]
    if not b64_list:
        raise HTTPException(status_code=400, detail="pdf_base64 为空")

    size_key = str(body.get("size_key") or "carton_100x100")
    width_mm = _parse_mm(body.get("width_mm"))
    height_mm = _parse_mm(body.get("height_mm"))
    options = _options_from_json_body(body)
    pdfs = [_decode_pdf_b64(b, i) for i, b in enumerate(b64_list, start=1)]
    try:
        data = thermal_labels_pdf(
            pdfs,
            size_key,
            width_mm=width_mm,
            height_mm=height_mm,
            options=options,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF 标签转换失败：{exc}") from exc

    size = resolve_size_params(size_key, width_mm, height_mm)
    return pdf_response(data, _pdf_filename(size))


@router.post("/api/pdf/convert_labels")
async def api_convert_labels(
    files: List[UploadFile] = File(...),
    size_key: str = Form("carton_100x100"),
    width_mm: Optional[str] = Form(None),
    height_mm: Optional[str] = Form(None),
    padding_mm: Optional[str] = Form(None),
    ignore_top_mm: Optional[str] = Form(None),
    ignore_bottom_mm: Optional[str] = Form(None),
    detect_dpi: Optional[str] = Form(None),
    custom_text: Optional[str] = Form(None),
):
    """模块 B：通用批量上传转换（同步，兼容旧客户端）。"""
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一个 PDF 文件")

    items = await _read_pdf_uploads(files)
    if not items:
        raise HTTPException(status_code=400, detail="上传文件为空")

    w_mm = _parse_mm(width_mm)
    h_mm = _parse_mm(height_mm)
    size = resolve_size_params(size_key, w_mm, h_mm)
    options = _options_from_form(
        padding_mm, ignore_top_mm, ignore_bottom_mm, detect_dpi, custom_text
    )
    try:
        processed = process_files_parallel(items, size, options=options)
        if not processed:
            raise HTTPException(status_code=400, detail="未检测到可处理的 PDF 内容")
        if len(processed) == 1:
            p = processed[0]
            return pdf_response(p.pdf_bytes, os.path.basename(p.name))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in processed:
                zf.writestr(os.path.basename(p.name), p.pdf_bytes)
        return file_response(buf.getvalue(), "标签转换.zip", "application/zip")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF 标签转换失败：{exc}") from exc


@router.post("/api/pdf/convert_labels/stream")
async def api_convert_labels_stream(
    files: List[UploadFile] = File(...),
    size_key: str = Form("carton_100x100"),
    width_mm: Optional[str] = Form(None),
    height_mm: Optional[str] = Form(None),
    padding_mm: Optional[str] = Form(None),
    ignore_top_mm: Optional[str] = Form(None),
    ignore_bottom_mm: Optional[str] = Form(None),
    detect_dpi: Optional[str] = Form(None),
    custom_text: Optional[str] = Form(None),
):
    """模块 B 流式版：SSE 实时推送进度，完成后按原文件名返回多个 PDF。"""
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一个 PDF 文件")

    w_mm = _parse_mm(width_mm)
    h_mm = _parse_mm(height_mm)
    options = _options_from_form(
        padding_mm, ignore_top_mm, ignore_bottom_mm, detect_dpi, custom_text
    )

    items = await _read_pdf_uploads(files)
    if not items:
        raise HTTPException(status_code=400, detail="上传文件为空")

    # 必须用同步 generate + StreamingResponse：Starlette 会放到线程池执行，
    # 若在 async def 里同步 for chunk in ... 会阻塞整个事件循环，导致 SSE 无法推送。
    def generate():
        yield from iter_convert_labels_sse(
            items, size_key, w_mm, h_mm, options=options
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
