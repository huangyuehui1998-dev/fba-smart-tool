"""票级数据（shipment_ticket）导入与查询。"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter()


def _call(fn, data: bytes, name: str):
    try:
        return fn(data, name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/tickets/import/preview")
async def api_ticket_import_preview(file: UploadFile = File(...)):
    """腾讯表格 / 运费测算表 / 九方单箱数据：自动识别，只预览不写库。"""
    from fba_tool.ticket_import import preview_ticket_import

    return _call(preview_ticket_import, await file.read(), file.filename or "")


@router.post("/api/tickets/import/apply")
async def api_ticket_import_apply(file: UploadFile = File(...)):
    from fba_tool.ticket_import import apply_ticket_import

    return _call(apply_ticket_import, await file.read(), file.filename or "")


@router.get("/api/tickets")
def api_tickets(batch: str = ""):
    from fba_tool.ticket_import import list_tickets

    items = list_tickets(batch)
    return {"items": items, "count": len(items)}


@router.post("/api/tickets/sta-placement-fee")
def api_sta_placement_fee(body: dict):
    """录入 STA 页面实际配置费，并与估算区间比较。"""
    from fba_tool.declared_value import record_sta_placement_fee

    try:
        return record_sta_placement_fee(
            str(body.get("fba_id") or ""),
            body.get("entered"),
            body.get("estimate_min"),
            body.get("estimate_max"),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
