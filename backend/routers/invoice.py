"""Step 4.5 — 货代发票预览、生成、编辑、导出。"""
from __future__ import annotations

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


@router.post("/api/export_invoice")
def api_export_invoice(body: InvoiceExportRequest):
    """导出最终发票 (.xlsx)；空单元格跳过写入，允许导出后手工补全。"""
    if not body.template_hash and not body.template_base64:
        raise HTTPException(status_code=400, detail="请提供 template_hash 或 template_base64")

    template_bytes = resolve_invoice_template_bytes(
        body.template_base64,
        body.template_hash,
        forwarder_id=body.forwarder_id,
    )

    draft = draft_from_payload(body)

    from fba_tool.invoice_step45 import export_rendered_workbook
    from fba_tool.univer_apply import ApplyRejected, apply_snapshot_values

    try:
        rendered = export_rendered_workbook(
            body.forwarder_id,
            draft.shipment_id,
            template_bytes,
            body.snapshot,
        )
        if rendered is not None:
            out = rendered
        elif body.snapshot:
            out = apply_snapshot_values(template_bytes, body.snapshot)
        else:
            out = export_invoice_xlsx(template_bytes, draft, forwarder_id=body.forwarder_id)
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
