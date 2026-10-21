from typing import List
from fastapi import APIRouter, File, UploadFile, HTTPException
import json
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

@router.post("/api/routing/preview")
async def api_routing_preview(files: List[UploadFile] = File(...)):
    """上传多个刷仓CSV，合并生成货代表数据预览"""
    if not files:
        raise HTTPException(status_code=400, detail="未上传文件")

    # 根据票数排序文件
    sorted_files = sorted(files, key=lambda f: extract_ticket_rank(f.filename or ""))
    
    all_specs = []
    all_items = []
    # 记录仓库到票序的映射，用于最后排序
    warehouse_rank_map = {}

    warnings: List[str] = []
    for idx, file in enumerate(sorted_files):
        filename = file.filename or "UNKNOWN.csv"
        rank = extract_ticket_rank(filename)
        try:
            content = await file.read()
            # 开启 allow_unassigned_fba 模式；file_name 留空，只取 CSV 自身的仓库代码（S8 D2）
            shipment = parse_csv_shipment(content, allow_unassigned_fba=True, file_name="")
            warehouse_code, _src, warn = resolve_routing_warehouse(shipment.warehouse_code, filename)
            if warn:
                warnings.append(warn)
            if warehouse_code not in warehouse_rank_map:
                warehouse_rank_map[warehouse_code] = rank if rank != 999 else 1000 + idx
            
            # 覆盖仓库代码
            if not shipment.box_specs.empty:
                shipment.box_specs["仓库代码"] = warehouse_code
                all_specs.append(shipment.box_specs)
                
            if not shipment.box_items.empty:
                shipment.box_items["仓库代码"] = warehouse_code
                all_items.append(shipment.box_items)
                
        except Exception as e:
            logger.exception(f"解析 {filename} 失败")
            raise HTTPException(status_code=400, detail=f"解析 {filename} 失败: {str(e)}")

    if not all_specs:
        raise HTTPException(status_code=400, detail="上传的文件未能解析出任何箱规数据")

    combined_specs = pd.concat(all_specs, ignore_index=True)
    combined_items = pd.concat(all_items, ignore_index=True) if all_items else None

    # 生成货代表
    forwarder_df = build_forwarder_df(combined_specs, combined_items)
    
    # 按预期的票序排序
    if not forwarder_df.empty:
        # 去掉小计行进行排序，然后再重新加上？
        # 其实可以直接利用 _ticket_rank
        # 为了不破坏原有的小计，我们自己处理排序：
        # 先分离出非小计行进行排序，然后重新调用小计？
        # forwarder_quote 提供了 sort_forwarder_by_warehouse_ticket，但它期望对象。我们可以自己构造。
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

    # 替换 NaN
    forwarder_df = forwarder_df.fillna("")
    from urllib.parse import quote
    from fastapi.responses import JSONResponse
    from fastapi.encoders import jsonable_encoder

    headers = {"X-Routing-Warnings": quote(json.dumps(warnings, ensure_ascii=False))} if warnings else {}
    return JSONResponse(jsonable_encoder(forwarder_df.to_dict(orient="records")), headers=headers)


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
