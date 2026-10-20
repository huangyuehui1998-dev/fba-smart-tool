"""Step 4 货件校验编排:workflow_json 解析与三维交叉校验运行。"""
from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, Iterator, List, Tuple

logger = logging.getLogger("fba_tool.shipment")

from fastapi import HTTPException

from fba_tool.box_label_mapping import mapping_to_records, match_local_to_amazon_boxes
from fba_tool.boxing import box_metrics, dataframe_to_sku_rows
from fba_tool.fba_parser import build_forwarder_df
from fba_tool.forwarder_quote import sort_forwarder_by_warehouse_ticket
from fba_tool.logistics_metrics import logistics_metrics_from_box_specs
from fba_tool.master_data_apply import apply_master_to_input_rows
from fba_tool.placement_fee import compute_locked_placement_fee
from fba_tool.shipment_cross_check import check_declared_box_specs
from fba_tool.shipment_validator import parse_uploads, validate_shipments
from fba_tool.shipment_parser import parse_csv_shipment
from fba_tool.shipment_serialize import csv_shipment_to_dict
from fba_tool.shipping_sheet import build_shipping_sheet_df, build_shipping_sheet_legend
from fba_tool.user_config import throw_ratio
from fba_tool.validation_progress import (
    ValidationProgress,
    ndjson_result,
    yield_progress_events,
)
from fba_tool.worker_packing_export import (
    build_worker_packing_horizontal_df,
    warehouse_labels_from_pairs,
)
from utils.serialization import df_to_records, editor_to_df, rows_to_df


def parse_workflow_json(workflow_json: str | None) -> Dict[str, Any]:
    if not workflow_json:
        return {}
    try:
        return json.loads(workflow_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"workflow_json 解析失败：{exc}") from exc


def run_shipment_validation(
    csv_payload: List[Tuple[str, bytes]],
    pdf_payload: List[Tuple[str, bytes]],
    wf: Dict[str, Any],
    *,
    progress: ValidationProgress | None = None,
):
    on_progress = progress.callback() if progress else None

    if progress:
        progress.report("正在加载主数据与装箱方案…", 3)

    editor_df = editor_to_df(wf.get("box_editor") or [])
    input_rows: List[Dict[str, Any]] = wf.get("rows") or []
    packing_mode = str(wf.get("packing_mode") or "amazon_led")
    merged_rows, _ = apply_master_to_input_rows(input_rows) if input_rows else ([], [])

    if progress:
        progress.report("正在解析 CSV / PDF 并匹配货件编号…", 8)

    parsed = parse_uploads(csv_payload, pdf_payload, on_progress=on_progress)
    result = validate_shipments(
        csv_payload,
        pdf_payload,
        parsed=parsed,
        step1_rows=merged_rows if merged_rows else None,
        on_progress=on_progress,
    )

    compare_errors = [e for e in result.errors if e.startswith("❌")]
    hard_fail = bool(compare_errors or not result.ok)

    return {
        "editor_df": editor_df,
        "input_rows": input_rows,
        "merged_rows": merged_rows,
        "packing_mode": packing_mode,
        "parsed": parsed,
        "result": result,
        "hard_fail": hard_fail,
    }


def build_validate_response(
    ctx: Dict[str, Any],
    ratio: float,
    *,
    progress: ValidationProgress | None = None,
) -> Dict[str, Any]:
    result = ctx["result"]
    editor_df = ctx["editor_df"]
    merged_rows = ctx["merged_rows"]
    packing_mode = ctx["packing_mode"]
    hard_fail = ctx["hard_fail"]

    response: Dict[str, Any] = {
        "ok": not hard_fail,
        "status_lines": result.status_lines,
        "errors": result.errors,
        "throw_ratio": ratio,
        "mapping_ok": None,
        "box_label_mapping": [],
        "actual_placement_fee": None,
        "packing_mode": packing_mode,
        "cross_check_ok": result.cross_check_ok,
        "worker_packing_ready": result.cross_check_ok and bool(result.worker_packing_rows),
        "declared_spec_warnings": [],
        "warehouse_warnings": list(getattr(result, "warehouse_warnings", []) or []),
    }

    if not hard_fail and result.ok:
        if progress:
            progress.report("正在建立本地箱号与亚马逊箱号映射…", 86)
        mapping_result = None
        if not editor_df.empty:
            mapping_result = match_local_to_amazon_boxes(editor_df, result.pairs)
            response["box_label_mapping"] = mapping_to_records(mapping_result)
            response["mapping_ok"] = mapping_result.ok
            if mapping_result.warnings:
                response["errors"] = list(response["errors"]) + mapping_result.warnings
            if packing_mode == "strict_local" and not mapping_result.ok:
                response["ok"] = False
                response["errors"] = list(response["errors"]) + mapping_result.errors
            elif packing_mode == "amazon_led" and mapping_result.errors:
                response["status_lines"] = list(response["status_lines"]) + [
                    "ℹ️ 亚马逊主导模式：本地箱号映射差异已记录，不阻断校验。"
                ] + mapping_result.errors
        else:
            response["mapping_ok"] = None
            if packing_mode == "amazon_led":
                response["status_lines"] = list(response["status_lines"]) + [
                    "✅ 亚马逊主导模式：按 CSV/PDF 箱唛数据生成工人装箱实操单（无需本地箱号映射）。"
                ]
            else:
                response["status_lines"] = list(response["status_lines"]) + [
                    "⚠️ 未传入 Step 2 装箱方案：严格模式下无法建立本地箱号映射。"
                ]

        if progress:
            progress.report("正在核对申报箱重/箱规…", 88)
        local_metrics = None
        if not editor_df.empty and merged_rows:
            local_metrics = box_metrics(editor_df, dataframe_to_sku_rows(rows_to_df(merged_rows)))
        spec_check = check_declared_box_specs(
            result.pairs,
            local_metrics,
            mapping_result.matches if mapping_result else None,
        )
        response["declared_spec_warnings"] = spec_check["rows"]
        if spec_check["warnings"]:
            response["status_lines"] = list(response["status_lines"]) + spec_check["warnings"]
        elif spec_check["compared_boxes"]:
            response["status_lines"] = list(response["status_lines"]) + [
                f"✅ 申报箱重/箱规与 Step 2 方案一致（已核对 {spec_check['compared_boxes']} 箱）"
            ]

        if progress:
            progress.report("正在生成货代表与物流指标…", 90)
        forwarder_df = build_forwarder_df(
            result.all_box_specs,
            result.all_box_items,
            throw_ratio=ratio,
        )
        forwarder_df = sort_forwarder_by_warehouse_ticket(forwarder_df, result.pairs)
        logistics = logistics_metrics_from_box_specs(result.all_box_specs, throw_ratio_val=ratio)

        if progress:
            progress.report("正在生成工人装箱单与发货表…", 94)
        worker_packing_preview = build_worker_packing_horizontal_df(
            result.pairs, step1_rows=merged_rows
        )
        worker_packing_warehouses = warehouse_labels_from_pairs(result.pairs)
        shipping_sheet_df = build_shipping_sheet_df(
            result.pairs, throw_ratio=ratio, step1_rows=merged_rows
        )
        shipping_sheet_legend = build_shipping_sheet_legend(merged_rows, result.pairs)

        shipments = []
        for pair in result.pairs:
            csv_b = result.csv_bytes.get(pair.shipment_id)
            pdf_b = result.pdf_bytes.get(pair.shipment_id)
            if csv_b and pdf_b:
                entry: Dict[str, Any] = {
                    "shipment_id": pair.shipment_id,
                    "warehouse": pair.warehouse_code,
                    "csv_base64": base64.b64encode(csv_b).decode("ascii"),
                    "pdf_base64": base64.b64encode(pdf_b).decode("ascii"),
                }
                try:
                    entry["parsed_shipment"] = csv_shipment_to_dict(parse_csv_shipment(csv_b, file_name=result.csv_names.get(pair.shipment_id, "")))
                except Exception:
                    pass
                shipments.append(entry)

        if progress:
            progress.report("正在锁定入库配置费…", 97)
        actual_warehouses = [pair.warehouse_code for pair in result.pairs]
        if merged_rows:
            fee_record = compute_locked_placement_fee(merged_rows, actual_warehouses)
            response["actual_placement_fee"] = fee_record
            if response.get("ok"):
                response["status_lines"] = list(response["status_lines"]) + [
                    f"💰 入库配置费已锁定：**${fee_record['locked_usd']:.2f}**（保守上限） · "
                    f"预期 ${fee_record['applicable_range_mid_usd']:.2f} · "
                    f"区间 ${fee_record['applicable_range_min_usd']:.2f}–"
                    f"${fee_record['applicable_range_max_usd']:.2f} "
                    f"（{fee_record['scenario_label']} · {fee_record['actual_location_count']} 仓 · "
                    f"{', '.join(fee_record['warehouse_regions'])}）"
                ]
        else:
            response["status_lines"] = list(response["status_lines"]) + [
                "⚠️ 未传入 Step 1 录入数据：无法将预估区间锁定为实际费用。"
            ]

        response.update(
            {
                "worker_packing_preview": df_to_records(worker_packing_preview),
                "worker_packing_warehouses": worker_packing_warehouses,
                "shipping_sheet": df_to_records(shipping_sheet_df),
                "shipping_sheet_legend": shipping_sheet_legend,
                "forwarder": df_to_records(forwarder_df),
                "shipments": shipments,
                "cargo_density": logistics["cargo_density"],
                "stowage_factor": logistics["stowage_factor"],
                "wm_ratio": logistics["wm_ratio"],
                "revenue_ton": logistics["revenue_ton"],
                "total_net_kg": logistics["total_net_kg"],
                "total_gross_kg": logistics["total_gross_kg"],
                "total_cbm": logistics["total_cbm"],
                "total_volumetric_weight_kg": logistics["total_volumetric_weight_kg"],
                "worker_packing_rows": result.worker_packing_rows,
            }
        )
    elif not editor_df.empty and hard_fail:
        response["status_lines"] = list(response["status_lines"]) + [
            "ℹ️ 三维交叉校验未通过，请修正 CSV/PDF 后重试。"
        ]

    if progress:
        progress.report("校验完成", 100)

    return response


def write_validation_snapshot(ctx: Dict[str, Any]) -> str | None:
    """两个校验接口共用。失败时记日志并返回 snapshot_warning，不再吞掉异常。"""
    if ctx.get("hard_fail"):
        return None
    try:
        from fba_tool.carton_store import snapshot_from_validation

        snapshot_from_validation(ctx)
    except Exception:
        logger.exception("申报快照写入失败")
        return "申报快照没有写入"
    return None


def iter_shipment_validation_events(
    csv_payload: List[Tuple[str, bytes]],
    pdf_payload: List[Tuple[str, bytes]],
    wf: Dict[str, Any],
    ratio: float,
) -> Iterator[str]:
    """NDJSON 流：progress 事件 + 最终 result。"""
    progress = ValidationProgress()
    yield from yield_progress_events(progress)

    progress.report("正在上传并读取文件…", 1)
    yield from yield_progress_events(progress)

    ctx = run_shipment_validation(csv_payload, pdf_payload, wf, progress=progress)
    yield from yield_progress_events(progress)

    response = build_validate_response(ctx, ratio, progress=progress)
    warning = write_validation_snapshot(ctx)
    if warning:
        response["snapshot_warning"] = warning
    yield from yield_progress_events(progress)
    yield ndjson_result(response)
