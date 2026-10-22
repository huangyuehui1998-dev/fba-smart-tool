"""Step 4.5 — 货代发票预览、生成、编辑、导出。"""
from __future__ import annotations

import base64

import pandas as pd
from fastapi import APIRouter, HTTPException

from fba_tool.invoice_automation import apply_grid_edits, build_invoice_preview, export_invoice_xlsx
from fba_tool.invoice_template_cache import store_template
from schemas import InvoiceExportRequest, InvoiceGenerateRequest, InvoicePreviewRequest
from services.invoice_service import (
    draft_from_payload,
    draft_to_dict,
    invoice_generate_payload,
    resolve_invoice_template_bytes,
)
from utils.responses import xlsx_response

router = APIRouter()


@router.post("/api/invoice/preview")
def api_invoice_preview(body: InvoicePreviewRequest):
    """解析发票模板结构，返回空值字段网格（预览态）。"""
    if not body.forwarder_id and not body.template_base64:
        raise HTTPException(status_code=400, detail="请提供 forwarder_id 或 template_base64")
    template_bytes = resolve_invoice_template_bytes(body.template_base64, forwarder_id=body.forwarder_id)
    try:
        draft = build_invoice_preview(template_bytes, forwarder_id=body.forwarder_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"模板解析失败：{exc}") from exc

    payload = draft_to_dict(draft)
    payload["template_hash"] = store_template(template_bytes)
    payload["phase"] = "preview"
    return payload


@router.post("/api/invoice/generate")
def api_invoice_generate(body: InvoiceGenerateRequest):
    """根据 Step 4 货件 CSV/PDF + 模板，自动匹配并填充字段（填充态）。"""
    return invoice_generate_payload(body)


@router.post("/api/generate_invoice")
def api_generate_invoice(body: InvoiceGenerateRequest):
    """智能生成货代发票草稿（CSV/PDF 精准映射 + 产品信息表 + DeepSeek 补全）。"""
    return invoice_generate_payload(body)


@router.post("/api/invoice/apply_edits")
def api_invoice_apply_edits(body: InvoiceExportRequest):
    """应用用户对发票网格的编辑，返回更新后的草稿。"""
    draft = draft_from_payload(body)
    grid_df = pd.DataFrame(body.fields)
    if grid_df.empty:
        grid_df = pd.DataFrame([{"字段": f.label, "值": f.value} for f in draft.fields])
    draft = apply_grid_edits(draft, grid_df)
    return draft_to_dict(draft)


def _preview_workbook_bytes(body: InvoiceExportRequest) -> bytes | None:
    """有货代时 template_base64 不是模板壳，而是预览手改。没选货代时它就是壳，不在这里再叠一次。"""
    if not body.forwarder_id or not body.template_base64:
        return None
    try:
        return base64.b64decode(body.template_base64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"模板 base64 解码失败：{exc}") from exc


@router.post("/api/export_invoice")
def api_export_invoice(body: InvoiceExportRequest):
    """导出最终发票 (.xlsx)。

    forwarder_id 决定官方模板壳（合并、公式、图片、隐藏表）。用户在预览里改过的格子
    来自三处，后者覆盖前者：请求 fields、template_base64 相对空白模板的差异、Univer 快照。
    空的 fields 不把已填格子擦成空白。
    """
    if not body.template_hash and not body.template_base64 and not body.forwarder_id:
        raise HTTPException(status_code=400, detail="请提供 template_hash 或 template_base64")

    template_bytes = resolve_invoice_template_bytes(
        body.template_base64,
        body.template_hash,
        forwarder_id=body.forwarder_id,
    )
    preview_bytes = _preview_workbook_bytes(body)

    draft = draft_from_payload(body)

    from fba_tool.invoice_step45 import overlay_preview_edits, recall_render
    from fba_tool.invoice_step45 import _apply_user_edits, export_field_keys
    from fba_tool.univer_apply import ApplyRejected, apply_cell_writes

    try:
        rendered = recall_render(body.forwarder_id, draft.shipment_id)
        if rendered is not None:
            out = rendered
            if draft.table_cells:
                out = apply_cell_writes(out, draft.table_cells, draft.template_sheet)
        elif body.snapshot and not draft.table_cells:
            out = template_bytes
        else:
            out = export_invoice_xlsx(template_bytes, draft, forwarder_id=body.forwarder_id)
        if preview_bytes is not None:
            out = overlay_preview_edits(out, template_bytes, preview_bytes)
        if body.snapshot:
            out = _apply_user_edits(out, template_bytes, body.snapshot, export_field_keys(draft))
    except ApplyRejected as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": exc.code, "cells": exc.cells, "message": exc.message},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    filename = f"货代发票_{draft.shipment_id}.xlsx"
    return xlsx_response(out, filename)
