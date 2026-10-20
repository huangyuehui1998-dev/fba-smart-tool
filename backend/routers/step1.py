"""Step 1 — 录入、解析、校验、预览、样表下载。"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from fba_tool.data_processing import (
    check_gross_weight_consistency,
    compute_step1_logistics_totals,
    load_from_excel,
    load_from_excel_detailed,
    parse_smart_text_detailed,
    validate_step1,
    with_computed_columns,
)
from fba_tool.deepseek_parser import parse_with_deepseek
from fba_tool.input_template import ensure_template_on_disk, generate_input_template_bytes
from fba_tool.master_data_apply import apply_master_to_input_rows, build_placement_unit_rows
from fba_tool.placement_fee import compute_shipment_placement_fees
from fba_tool.user_config import throw_ratio
from schemas import ComputePreviewRequest, InputRowsRequest, TextParseRequest
from utils.responses import xlsx_response
from utils.serialization import (
    df_to_records,
    rows_to_df,
    rows_to_df_with_master,
    validation_errors_payload,
)

router = APIRouter()


@router.post("/api/parse_text")
def api_parse_text_local(body: TextParseRequest):
    """本地规则解析（Tab/逗号/空格分隔，可带表头）。解析失败返回 422，并逐条列出 {row, field, value, message}。"""
    df, errors, warnings = parse_smart_text_detailed(body.text)
    if errors:
        head = "；".join(e["message"] for e in errors[:5])
        more = f"（共 {len(errors)} 处）" if len(errors) > 5 else ""
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"本地规则解析失败：{head}{more}",
                "errors": errors,
                "warnings": warnings,
            },
        )
    return {
        "count": len(df),
        "rows": df_to_records(df),
        "warnings": warnings,
    }


@router.post("/api/parse_text/deepseek")
def api_parse_text_deepseek(body: TextParseRequest):
    """DeepSeek 智能解析自然语言/表格文本。"""
    try:
        df = parse_with_deepseek(
            body.text,
            api_key=body.api_key,
            model=body.model,
            temperature=body.temperature,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"DeepSeek 调用失败：{exc}") from exc
    return {
        "count": len(df),
        "rows": df_to_records(df),
    }


@router.post("/api/parse_excel")
async def api_parse_excel(file: UploadFile = File(...)):
    """上传 Excel 样表，解析 SKU 录入数据。"""
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="请上传 .xlsx 或 .xls 文件")
    try:
        content = await file.read()
        df, fnsku_map, errors, warnings = load_from_excel_detailed(content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"样表解析失败：{exc}") from exc
    if errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "样表解析失败：" + "；".join(e["message"] for e in errors[:5])
                + (f"（共 {len(errors)} 处）" if len(errors) > 5 else ""),
                "errors": errors,
                "warnings": warnings,
            },
        )
    return {
        "count": len(df),
        "rows": df_to_records(df),
        "fnsku_overrides": fnsku_map,
        "warnings": warnings,
    }


@router.post("/api/validate_input")
def api_validate_input(body: InputRowsRequest):
    """校验 Step1 必填字段。"""
    df = rows_to_df_with_master(body.rows)
    errors = validate_step1(df)
    return {
        "valid": len(errors) == 0,
        "errors": validation_errors_payload(errors),
    }


@router.post("/api/compute_preview")
def api_compute_preview(body: ComputePreviewRequest):
    """计算预计整箱数、尾数、总净重/毛重，及总方数、总体积重。"""
    merged_rows, data_sources = apply_master_to_input_rows(body.rows)
    df = rows_to_df(merged_rows)
    computed = with_computed_columns(df)
    from fba_tool.boxing import box_metrics, dataframe_to_sku_rows, generate_box_plan, plans_to_editor_df
    from fba_tool.user_config import weight_limit_kg

    sku_rows = dataframe_to_sku_rows(computed)
    plans, _tail = generate_box_plan(sku_rows)
    metrics = box_metrics(plans_to_editor_df(plans), sku_rows)
    ratio = float(body.throw_ratio if body.throw_ratio is not None else throw_ratio())
    totals = compute_step1_logistics_totals(df, throw_ratio_val=ratio)
    placement = compute_shipment_placement_fees(build_placement_unit_rows(body.rows))
    warnings = check_gross_weight_consistency(computed)
    limit = float(weight_limit_kg())
    for row in df_to_records(metrics):
        if int(row.get("SKU种类") or 0) > 1 and float(row.get("毛重(kg)") or 0) > limit:
            warnings.append(
                {
                    "row_index": int(row["箱号"]),
                    "sku": f"箱{int(row['箱号'])}",
                    "kind": "mixed_over_limit",
                    "requires_confirm": True,
                    "suggested_gross_kg": None,
                    "declared_kg": row.get("毛重(kg)"),
                    "expected_kg": limit,
                    "message": f"混装箱 {int(row['箱号'])} 毛重 {row.get('毛重(kg)')} kg 超过上限 {limit:g} kg",
                }
            )
    from fba_tool.master_db import get_product_by_sku

    gaps = []
    for row in body.rows:
        sku = str(row.get("SKU简称") or row.get("sku") or "").strip()
        if not sku:
            continue
        product = get_product_by_sku(sku) or {}
        missing = []
        if not str(product.get("asin") or "").strip():
            missing.append("asin")
        if not any(str(product.get(key) or "").strip() for key in ("chinese_name", "english_name", "local_name")):
            missing.append("name")
        if not all(product.get(key) not in (None, "", 0) for key in ("unit_length", "unit_width", "unit_height")):
            missing.append("unit_dims")
        if missing:
            gaps.append({"sku": sku, "missing": missing})
    return {
        "rows": df_to_records(computed),
        "master_gaps": gaps,
        "merged_rows": merged_rows,
        "data_sources": data_sources,
        "total_cbm": totals["total_cbm"],
        "total_volumetric_weight": totals["total_volumetric_weight_kg"],
        "throw_ratio": ratio,
        "cargo_density": totals["cargo_density"],
        "stowage_factor": totals["stowage_factor"],
        "wm_ratio": totals["wm_ratio"],
        "revenue_ton": totals["revenue_ton"],
        "total_net_kg": totals["total_net_kg"],
        "total_gross_kg": totals["total_gross_kg"],
        "box_metrics": df_to_records(metrics),
        "weight_warnings": warnings,
        "cost_dashboard": {
            "placement": placement,
        },
    }


@router.get("/api/input_template")
def api_download_input_template():
    """下载发货录入样表 (.xlsx)。"""
    ensure_template_on_disk()
    data = generate_input_template_bytes()
    return xlsx_response(data, "发货录入样表.xlsx")
