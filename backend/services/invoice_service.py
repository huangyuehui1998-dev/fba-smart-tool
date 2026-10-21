"""Step 4.5 发票编排:草稿组装、模板字节解析、发票生成 payload。"""
from __future__ import annotations

import base64
from typing import Any, Dict

from fastapi import HTTPException

from fba_tool.forwarder_registry import get_template_bytes as forwarder_template_bytes
from fba_tool.invoice_automation import (
    InvoiceDraft,
    InvoiceField,
    build_invoice_draft,
)
from fba_tool.invoice_template_cache import get_template, store_template
from fba_tool.logistics_metrics import logistics_metrics_from_box_specs
from fba_tool.shipment_serialize import resolve_csv_shipment
from fba_tool.template_loader import template_path
from fba_tool.user_config import throw_ratio
from schemas.invoice import InvoiceExportRequest, InvoiceGenerateRequest
from utils.serialization import df_to_records


def draft_from_payload(data: InvoiceExportRequest) -> InvoiceDraft:
    table_cells: list[Dict[str, Any]] = []
    fields = []
    for item in data.fields:
        cell = str(item.get("cell", item.get("单元格", ""))).strip()
        field_key = str(item.get("key", item.get("字段", "")))
        value = item.get("value", item.get("值", ""))
        required = bool(item.get("required", item.get("必填") == "是"))
        if cell:
            table_cells.append(
                {
                    "cell": cell.upper(),
                    "value": value,
                    "field_key": field_key,
                    "required": required,
                }
            )
        fields.append(
            InvoiceField(
                key=field_key,
                label=str(item.get("label", item.get("字段", field_key))),
                value=value,
                source=item.get("source", "green"),
                cell=cell,
                required=required,
            )
        )

    table_keys = {c.get("field_key") for c in table_cells}
    is_table = len(table_cells) >= 3 and (
        "sku" in table_keys
        or ("fba_id" in table_keys and "box_range" in table_keys)
        or ("shipment_id" in table_keys and "box_range" in table_keys)
    )
    if is_table:
        ref_cells = [c for c in table_cells if c.get("field_key") == "reference_id"]
        filled_ref = next((c["value"] for c in ref_cells if str(c.get("value") or "").strip()), None)
        if filled_ref:
            for cell in ref_cells:
                if not str(cell.get("value") or "").strip():
                    cell["value"] = filled_ref

    return InvoiceDraft(
        shipment_id=data.shipment_id,
        warehouse_code=data.warehouse_code,
        fields=[] if is_table else fields,
        template_sheet=data.template_sheet,
        table_cells=table_cells if is_table else [],
        is_table_mode=is_table,
    )


def draft_to_dict(draft: InvoiceDraft) -> Dict[str, Any]:
    return {
        "shipment_id": draft.shipment_id,
        "warehouse_code": draft.warehouse_code,
        "template_sheet": draft.template_sheet,
        "grid": df_to_records(draft.to_grid_df()),
        "cells": draft.to_cells_list(),
        "missing_required": draft.missing_required(),
        "warnings": list(draft.warnings or []),
    }


def resolve_invoice_template_bytes(
    template_base64: str | None = None,
    template_hash: str | None = None,
    forwarder_id: str | None = None,
) -> bytes:
    """选定货代时返回官方模板壳，不用请求里的 template_base64 换掉整本工作簿。

    预览里改过的格子不在这里处理。导出接口会把 template_base64、fields 和 Univer
    快照里相对这份空白模板的差异写回去。
    """
    if forwarder_id:
        data = forwarder_template_bytes(forwarder_id)
        store_template(data)
        return data
    if template_hash:
        cached = get_template(template_hash)
        if cached:
            return cached
        if not template_base64:
            raise HTTPException(
                status_code=400,
                detail="模板缓存已过期，请重新选择货代或随请求附带 template_base64",
            )
    if template_base64:
        try:
            data = base64.b64decode(template_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"模板 base64 解码失败：{exc}") from exc
        store_template(data)
        return data
    default_tpl = template_path("待填写的发票模板.xlsx") or template_path("发票模板.xlsx")
    if default_tpl and default_tpl.exists():
        data = default_tpl.read_bytes()
        store_template(data)
        return data
    raise HTTPException(status_code=400, detail="未找到发票模板，请选择货代或上传 template_base64")


def invoice_generate_payload(body: InvoiceGenerateRequest) -> Dict[str, Any]:
    csv_bytes = b""
    if body.csv_base64:
        try:
            csv_bytes = base64.b64decode(body.csv_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"CSV base64 解码失败：{exc}") from exc

    if not csv_bytes and not body.parsed_shipment:
        raise HTTPException(status_code=400, detail="需要 csv_base64 或 parsed_shipment")

    pdf_bytes = b""
    if body.pdf_base64:
        try:
            pdf_bytes = base64.b64decode(body.pdf_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"PDF base64 解码失败：{exc}") from exc

    template_bytes = resolve_invoice_template_bytes(
        body.template_base64,
        forwarder_id=body.forwarder_id,
    )

    use_workflow = body.workflow_json is not None or bool(body.forwarder_id)
    from fba_tool.invoice_rules import InvoiceBlocked
    from routers.invoice_export import WarehouseUndecided

    try:
        draft, usage_acc = build_invoice_draft(
            csv_bytes,
            pdf_bytes,
            template_bytes,
            api_key=body.api_key if not use_workflow else None,
            model=body.model,
            temperature=body.temperature,
            workflow_json=body.workflow_json,
            po_number=body.po_number or "",
            use_workflow_fill=use_workflow,
            forwarder_id=body.forwarder_id,
            parsed_shipment=body.parsed_shipment,
            warehouse=body.warehouse or "",
        )
    except InvoiceBlocked as exc:
        raise HTTPException(status_code=409, detail={"detail": str(exc), "blocking": exc.blocking}) from exc
    except WarehouseUndecided as exc:
        message = str(exc)
        raise HTTPException(
            status_code=422,
            detail={
                "code": "warehouse_undecided",
                "message": message,
                "detail": message,
                "address": getattr(exc, "address", ""),
                "warehouse_candidates": exc.candidates,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"发票生成失败：{exc}") from exc

    if body.shipment_id and draft.shipment_id != body.shipment_id:
        raise HTTPException(
            status_code=400,
            detail=f"货件编号不匹配：请求 {body.shipment_id}，解析得到 {draft.shipment_id}",
        )

    payload = draft_to_dict(draft)
    payload["template_hash"] = store_template(template_bytes)
    payload["phase"] = "filled"
    if body.forwarder_id:
        payload["forwarder_id"] = body.forwarder_id
    if body.api_key and usage_acc is not None:
        payload["total_tokens"] = usage_acc.total_tokens
        payload["estimated_cost_rmb"] = usage_acc.estimated_cost_rmb()
    ship = resolve_csv_shipment(parsed_shipment=body.parsed_shipment, csv_bytes=csv_bytes or None)
    shipment_metrics = logistics_metrics_from_box_specs(ship.box_specs, throw_ratio_val=throw_ratio())
    payload["revenue_ton"] = shipment_metrics.get("revenue_ton")
    payload["wm_ratio"] = shipment_metrics.get("wm_ratio")
    return payload
