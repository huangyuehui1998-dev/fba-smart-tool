import asyncio
import json
import re
from typing import Any, Dict, List, Tuple
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
import pandas as pd
from loguru import logger

from fba_tool.routing_service import (
    extract_ticket_rank,
    extract_warehouse_from_filename,
    resolve_routing_warehouse,
    strict_warehouse_from_filename,
)
from fba_tool.shipment_parser import parse_csv_shipment
from fba_tool.forwarder_quote import build_forwarder_df
from fba_tool.excel_export import export_forwarder_quote
from fba_tool.session_store import save_routing_snapshot, list_routing_snapshots, delete_routing_snapshot
from routers.shipment import xlsx_response
from pydantic import BaseModel
from typing import Any, Dict

router = APIRouter(tags=["routing"])

class RoutingSnapshotSaveBody(BaseModel):
    name: str
    forwarder_data: List[Dict[str, Any]]

class RoutingExportBody(BaseModel):
    forwarder: List[Dict[str, Any]]

def _process_routing_batch_sync(file_payloads: List[Tuple[str, bytes]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """在工作线程中同步执行重度 Pandas 解析与数据聚合，不阻塞 FastAPI 主事件循环。"""
    sorted_files = sorted(file_payloads, key=lambda item: extract_ticket_rank(item[0]))
    all_specs = []
    all_items = []
    warehouse_rank_map = {}
    warnings: List[str] = []

    for idx, (filename, content) in enumerate(sorted_files):
        rank = extract_ticket_rank(filename)
        try:
            shipment = parse_csv_shipment(content, allow_unassigned_fba=True, file_name="")
            warehouse_code, _src, warn = resolve_routing_warehouse(shipment.warehouse_code, filename, is_routing_mode=True)
            if warn:
                warnings.append(warn)
            if warehouse_code not in warehouse_rank_map:
                warehouse_rank_map[warehouse_code] = rank if rank != 999 else 1000 + idx

            if not shipment.box_specs.empty:
                shipment.box_specs["仓库代码"] = warehouse_code
                shipment.box_specs["原始仓库代码"] = shipment.warehouse_code or "UNKN"
                all_specs.append(shipment.box_specs)

            if not shipment.box_items.empty:
                shipment.box_items["仓库代码"] = warehouse_code
                shipment.box_items["原始仓库代码"] = shipment.warehouse_code or "UNKN"
                all_items.append(shipment.box_items)
        except Exception as e:
            logger.exception(f"解析 {filename} 失败")
            raise HTTPException(status_code=400, detail=f"解析 {filename} 失败: {str(e)}")

    if not all_specs:
        raise HTTPException(status_code=400, detail="上传文件未能解析出任何装箱数据")

    combined_specs = pd.concat(all_specs, ignore_index=True)
    combined_items = pd.concat(all_items, ignore_index=True) if all_items else None

    forwarder_df = build_forwarder_df(combined_specs, combined_items)

    if not forwarder_df.empty:
        from fba_tool.forwarder_quote import _strip_subtotal_rows, append_warehouse_subtotals
        detail = _strip_subtotal_rows(forwarder_df)
        if not detail.empty:
            work = detail.copy()
            work["_ticket_rank"] = work["仓库代码"].astype(str).map(lambda w: warehouse_rank_map.get(w, 9999))
            sort_cols = ["_ticket_rank", "仓库代码"]
            if "SKU" in work.columns:
                sort_cols.append("SKU")
            work = work.sort_values(sort_cols, kind="stable").drop(columns=["_ticket_rank"])
            forwarder_df = append_warehouse_subtotals(work)

    forwarder_df = forwarder_df.fillna("")
    from fastapi.encoders import jsonable_encoder
    records = jsonable_encoder(forwarder_df.to_dict(orient="records"))
    return records, warnings


@router.post("/api/routing/preview")
async def api_routing_preview(files: List[UploadFile] = File(...)):
    """上传刷仓CSV合并生成货代表预估（带 DoS 熔断与工作线程池卸载）。"""
    if not files:
        raise HTTPException(status_code=400, detail="未上传文件")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="单次批量上传最多支持 50 个文件")

    total_bytes = 0
    file_payloads: List[Tuple[str, bytes]] = []
    for file in files:
        content = await file.read()
        total_bytes += len(content)
        if total_bytes > 50 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="批量上传总文件大小超过 50MB 限制")
        file_payloads.append((file.filename or "UNKNOWN.csv", content))

    forwarder_records, warnings = await asyncio.to_thread(_process_routing_batch_sync, file_payloads)

    clean_warnings = [re.sub(r"[\r\n]+", " ", str(w)).strip() for w in warnings if w]
    encoded_warn = quote(json.dumps(clean_warnings, ensure_ascii=False))
    if len(encoded_warn) > 3500:
        clean_warnings = clean_warnings[:10] + ["... (告警较多已截断)"]
        encoded_warn = quote(json.dumps(clean_warnings, ensure_ascii=False))
    headers = {"X-Routing-Warnings": encoded_warn} if clean_warnings else {}
    return JSONResponse(forwarder_records, headers=headers)


@router.post("/api/routing/export")
def api_routing_export(body: RoutingExportBody):
    """导出刷仓货代表 Excel"""
    if not body.forwarder:  # S8 D15：空数据是用户输入问题，返回 400 而不是被包成 500
        raise HTTPException(status_code=400, detail="数据为空：请先生成货代表预览")
    try:
        df = pd.DataFrame(body.forwarder)
        return xlsx_response(export_forwarder_quote(df), "刷仓货代表.xlsx")
    except Exception as exc:
        logger.exception("刷仓货代表导出失败")
        raise HTTPException(status_code=500, detail=f"导出失败: {exc}")

@router.post("/api/routing/snapshots/{task_id}")
def api_save_routing_snapshot(task_id: str, body: RoutingSnapshotSaveBody):
    """保存当前刷仓生成的货代表数据为历史快照"""
    if not body.forwarder_data:
        raise HTTPException(status_code=400, detail="数据为空")
    result = save_routing_snapshot(task_id, body.name, body.forwarder_data)
    return result

@router.get("/api/routing/snapshots/{task_id}")
def api_list_routing_snapshots(task_id: str):
    """获取当前任务下所有的刷仓快照列表"""
    return {"snapshots": list_routing_snapshots(task_id)}

@router.delete("/api/routing/snapshots/{snapshot_id}")
def api_delete_routing_snapshot(snapshot_id: str):
    """删除指定的刷仓快照"""
    if delete_routing_snapshot(snapshot_id):
        return {"ok": True}
    raise HTTPException(status_code=404, detail="快照不存在或删除失败")
