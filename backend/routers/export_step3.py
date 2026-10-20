"""Step 3 — 前期报表导出（内部留档 / Send to Amazon）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from fba_tool.boxing import dataframe_to_sku_rows
from fba_tool.excel_export import build_box_matrix
from fba_tool.export_service import step3_export_bundle
from schemas import ExportStep3Request
from utils.responses import xlsx_response
from utils.serialization import df_to_records, editor_to_df, rows_to_df_with_master

router = APIRouter()


def _check_weight(body) -> None:
    from fba_tool.weight_gate import raise_if_weight_unconfirmed

    raise_if_weight_unconfirmed(body.rows, body.confirm_weight_warnings, body.box_editor)


def _check_not_oversold(editor_df, sku_rows) -> None:
    """S8 D1：导出前再核一次——箱单里任何 SKU 的件数都不能超过发货总数。"""
    if editor_df.empty:
        return
    packed = editor_df.groupby("SKU简称")["数量"].sum().to_dict()
    totals = {s.sku: int(s.total_qty) for s in sku_rows}
    over = [f"{k} 箱单 {int(v)} 件 > 计划 {totals[k]} 件" for k, v in packed.items() if k in totals and int(v) > totals[k]]
    if over:
        raise HTTPException(status_code=400, detail="箱单件数超过发货计划，已拦截导出：" + "；".join(over))


@router.post("/api/export/step3/preview")
def api_export_step3_preview(body: ExportStep3Request):
    """预览内部留档 / Send to Amazon 矩阵（JSON）。"""
    df = rows_to_df_with_master(body.rows)
    editor_df = editor_to_df(body.box_editor)
    if editor_df.empty:
        raise HTTPException(status_code=400, detail="装箱方案为空")
    matrix = build_box_matrix(editor_df)
    return {
        "matrix": df_to_records(matrix),
        "box_count": int(editor_df["箱号"].astype(int).max()) if not editor_df.empty else 0,
        "sku_count": int(editor_df["SKU简称"].nunique()) if not editor_df.empty else 0,
    }


@router.post("/api/export/step3/internal")
def api_export_internal(body: ExportStep3Request):
    """导出内部留档表 (.xlsx)。"""
    _check_weight(body)
    df = rows_to_df_with_master(body.rows)
    editor_df = editor_to_df(body.box_editor)
    sku_rows = dataframe_to_sku_rows(df)
    _check_not_oversold(editor_df, sku_rows)
    _, internal_bytes, _ = step3_export_bundle(editor_df, sku_rows, body.fnsku_overrides)
    return xlsx_response(internal_bytes, "内部留档表.xlsx")


@router.post("/api/export/step3/amazon")
def api_export_amazon(body: ExportStep3Request):
    """导出 Send to Amazon 模板 (.xlsx)。"""
    _check_weight(body)
    df = rows_to_df_with_master(body.rows)
    editor_df = editor_to_df(body.box_editor)
    sku_rows = dataframe_to_sku_rows(df)
    _check_not_oversold(editor_df, sku_rows)
    _, _, amazon_bytes = step3_export_bundle(editor_df, sku_rows, body.fnsku_overrides)
    if getattr(body, "fba_id", ""):
        try:
            from fba_tool.carton_store import snapshot_from_editor

            snapshot_from_editor(body.fba_id, body.box_editor, body.rows)
        except Exception:
            pass
    return xlsx_response(amazon_bytes, "Send to Amazon表格.xlsx")
