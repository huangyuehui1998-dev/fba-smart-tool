"""Step 2 — 自动排箱、每箱指标、尾数池、尾数分配。"""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, HTTPException

from fba_tool.boxing import (
    box_metrics,
    calculate_boxes,
    dataframe_to_sku_rows,
    plans_to_editor_df,
)
from fba_tool.data_processing import validate_step1
from fba_tool.fba_compliance import boxing_api_compliance
from fba_tool.user_config import weight_limit_kg
from schemas import BoxEditorRequest, InputRowsRequest, TailAssignRequest
from services.boxing_service import boxing_response_payload, compute_tail_pool
from utils.serialization import (
    df_to_records,
    editor_to_df,
    rows_to_df_with_master,
    validation_errors_payload,
)

router = APIRouter()


@router.post("/api/calculate_boxes")
def api_calculate_boxes(body: InputRowsRequest):
    """根据录入数据自动生成装箱方案。"""
    df = rows_to_df_with_master(body.rows)
    errors = validate_step1(df)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "录入数据未通过校验", "errors": validation_errors_payload(errors)},
        )
    sku_rows = dataframe_to_sku_rows(df)
    plans, tail_df, warnings = calculate_boxes(sku_rows)
    editor_df = plans_to_editor_df(plans)
    metrics = box_metrics(editor_df, sku_rows)
    payload = boxing_response_payload(
        editor_df, sku_rows, metrics, tail_df=tail_df, transport_mode=body.transport_mode
    )
    payload["warnings"] = warnings
    return payload


@router.post("/api/box_metrics")
def api_box_metrics(body: BoxEditorRequest):
    """对可编辑装箱方案计算每箱指标。"""
    df = rows_to_df_with_master(body.rows)
    editor_df = editor_to_df(body.box_editor)
    sku_rows = dataframe_to_sku_rows(df)
    metrics = box_metrics(editor_df, sku_rows)
    enriched, compliance = boxing_api_compliance(
        editor_df, sku_rows, metrics, transport_mode=body.transport_mode
    )
    return {
        "metrics": df_to_records(enriched),
        "has_overweight": bool(enriched["超重"].any()) if not enriched.empty else False,
        "weight_limit_kg": weight_limit_kg(),
        "fba_compliance": compliance,
        "has_fba_block": bool(compliance.get("blocked")),
    }


@router.post("/api/tail_pool")
def api_tail_pool(body: BoxEditorRequest):
    """计算待排尾数池。"""
    df = rows_to_df_with_master(body.rows)
    editor_df = editor_to_df(body.box_editor)
    sku_rows = dataframe_to_sku_rows(df)
    tail_df = compute_tail_pool(editor_df, sku_rows)
    return {"tail_pool": df_to_records(tail_df)}


def tail_remaining(editor_df: pd.DataFrame, sku_rows) -> dict:
    """每个 SKU 还没排进箱的件数（发货总数 − 已在箱单里的数量）。"""
    packed = editor_df.groupby("SKU简称")["数量"].sum().to_dict() if not editor_df.empty else {}
    return {s.sku: int(s.total_qty) - int(packed.get(s.sku, 0)) for s in sku_rows}


def validate_tail_assign(editor_df: pd.DataFrame, sku_rows, sku: str, qty: int, target_box: int) -> None:
    """S8 D1：尾数分配必须在尾数池范围内，防止超发。"""
    remain = tail_remaining(editor_df, sku_rows)
    if sku not in remain:
        raise HTTPException(400, f"SKU {sku} 不在本次发货清单里，不能分配尾数")
    left = remain[sku]
    if left <= 0:
        raise HTTPException(400, f"SKU {sku} 没有待排尾数（已全部装箱）")
    if qty > left:
        raise HTTPException(400, f"SKU {sku} 尾数只剩 {left} 件，不能分配 {qty} 件")
    boxes = pd.to_numeric(editor_df["箱号"], errors="coerce").dropna() if not editor_df.empty else pd.Series(dtype=float)
    max_box = int(boxes.max()) if len(boxes) else 0
    if target_box > max_box + 1:
        raise HTTPException(400, f"目标箱号 {target_box} 不存在：现有 1–{max_box} 箱，最多新开第 {max_box + 1} 箱")


@router.post("/api/box/assign_tail")
def api_assign_tail(body: TailAssignRequest):
    """将尾数分配到指定箱号（返回更新后的 box_editor）。"""
    df = rows_to_df_with_master(body.rows)
    editor_df = editor_to_df(body.box_editor)
    sku_rows = dataframe_to_sku_rows(df)
    validate_tail_assign(editor_df, sku_rows, body.sku, body.qty, body.target_box)
    new_row = pd.DataFrame(
        [{"箱号": body.target_box, "来源": "混装", "SKU简称": body.sku, "数量": body.qty}]
    )
    editor_df = pd.concat([editor_df, new_row], ignore_index=True)
    metrics = box_metrics(editor_df, sku_rows)
    payload = boxing_response_payload(
        editor_df, sku_rows, metrics, transport_mode=body.transport_mode
    )
    return {
        "box_editor": payload["box_editor"],
        "metrics": payload["metrics"],
        "has_overweight": payload["has_overweight"],
        "fba_compliance": payload["fba_compliance"],
        "has_fba_block": payload["has_fba_block"],
    }
