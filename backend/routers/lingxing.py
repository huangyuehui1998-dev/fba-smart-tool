"""领星 MCP 配置、一键拉取（NDJSON）与主表预览确认。"""
from __future__ import annotations

import json
import threading
from typing import Iterator, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from fba_tool.lingxing_mcp_client import DEFAULT_MCP_URL
from fba_tool.lingxing_preview import (
    LingxingPreviewError,
    confirm_lingxing_preview,
    latest_preview_payload,
    serialize_preview,
)
from fba_tool.lingxing_sync import (
    iter_full_sync_events,
    load_lingxing_settings,
    mask_key,
    save_lingxing_settings,
)
from fba_tool.master_db import (
    get_latest_lingxing_sync_run,
    get_lingxing_sync_run,
    list_lingxing_shops,
    list_lingxing_stock_alerts,
    list_lingxing_sync_diffs,
)

router = APIRouter()
from fba_tool import lingxing_scheduler as sched

_sync_lock = sched.SYNC_LOCK  # 与定时同步共用一把锁，防重入


class LingxingSettingsUpdate(BaseModel):
    mcp_key: Optional[str] = Field(None, description="领星 MCP Key；空字符串表示不修改")
    mcp_url: Optional[str] = Field(None, description="MCP Streamable HTTP URL")


class LingxingConfirmItem(BaseModel):
    sku: str
    fields: List[str] = Field(default_factory=list)


class LingxingConfirmBody(BaseModel):
    run_id: int
    items: List[LingxingConfirmItem] = Field(default_factory=list)


@router.get("/api/lingxing/settings")
def api_lingxing_settings():
    settings = load_lingxing_settings()
    key = settings.get("mcp_key") or ""
    return {
        "mcp_url": settings.get("mcp_url") or DEFAULT_MCP_URL,
        "mcp_key_set": bool(key),
        "mcp_key_hint": mask_key(key),
    }


@router.put("/api/lingxing/settings")
def api_lingxing_settings_update(body: LingxingSettingsUpdate):
    key = body.mcp_key
    if key is not None and not str(key).strip():
        key = None
    from fba_tool.secret_store import SecretStoreError

    try:
        saved = save_lingxing_settings(mcp_key=key, mcp_url=body.mcp_url)
    except SecretStoreError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "ok": True,
        "mcp_url": saved.get("mcp_url") or DEFAULT_MCP_URL,
        "mcp_key_set": bool(saved.get("mcp_key")),
        "mcp_key_hint": mask_key(saved.get("mcp_key") or ""),
    }


@router.get("/api/lingxing/last-run")
def api_lingxing_last_run():
    run = get_latest_lingxing_sync_run()
    if not run:
        return {
            "run": None,
            "shops": list_lingxing_shops(),
            "alerts": list_lingxing_stock_alerts(),
            "preview": None,
        }
    diffs = list_lingxing_sync_diffs(int(run["id"]))
    preview = latest_preview_payload()
    return {
        "run": run,
        "diffs": diffs,
        "shops": list_lingxing_shops(),
        "alerts": list_lingxing_stock_alerts(),
        "preview": preview,
    }


@router.get("/api/lingxing/sync/preview")
def api_lingxing_sync_preview(run_id: Optional[int] = None):
    if run_id is None:
        payload = latest_preview_payload()
        if not payload:
            return {"run_id": None, "status": "none", "groups": {}, "summary": {}, "pending": False}
        return payload
    run = get_lingxing_sync_run(int(run_id))
    if not run:
        raise HTTPException(status_code=404, detail="找不到该次拉取记录")
    payload = serialize_preview(int(run_id))
    from fba_tool.lingxing_preview import CONFIRMABLE_STATUSES

    payload["pending"] = str(run.get("status") or "") in CONFIRMABLE_STATUSES
    return payload


@router.post("/api/lingxing/sync/confirm")
def api_lingxing_sync_confirm(body: LingxingConfirmBody):
    try:
        return confirm_lingxing_preview(
            body.run_id,
            [{"sku": item.sku, "fields": item.fields} for item in body.items],
        )
    except LingxingPreviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/api/lingxing/alerts")
def api_lingxing_alerts():
    items = list_lingxing_stock_alerts()
    return {"items": items, "count": len(items)}


@router.post("/api/lingxing/sync/stream")
def api_lingxing_sync_stream():
    if not _sync_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="领星同步正在进行，请稍候")

    def generate() -> Iterator[str]:
        try:
            for event in iter_full_sync_events():
                yield json.dumps(event, ensure_ascii=False) + "\n"
        finally:
            _sync_lock.release()

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------- S5 定时同步
class ScheduleUpdate(BaseModel):
    enabled: Optional[bool] = None
    interval_minutes: Optional[int] = None
    max_retries: Optional[int] = None
    retry_delay_seconds: Optional[int] = None
    auto_apply: Optional[bool] = None


@router.get("/api/lingxing/schedule")
def api_lingxing_schedule():
    return {"config": sched.load_schedule(), "status": sched.status(),
            "limits": {"min_interval": sched.MIN_INTERVAL, "max_interval": sched.MAX_INTERVAL}}


@router.put("/api/lingxing/schedule")
def api_lingxing_schedule_update(body: ScheduleUpdate):
    try:
        cfg = sched.save_schedule(body.model_dump() if hasattr(body, "model_dump") else body.dict())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"config": cfg, "status": sched.status()}


@router.post("/api/lingxing/schedule/run-now")
def api_lingxing_schedule_run_now():
    """手动“立即重试/立即同步”：走和定时同步同一条路径（带重试、自动写入、日志）。"""
    if sched.SYNC_LOCK.locked():
        raise HTTPException(status_code=409, detail="领星同步正在进行，请稍候")
    return sched.run_once(trigger=sched.TRIGGER_MANUAL_RETRY)


@router.get("/api/lingxing/runs")
def api_lingxing_runs(limit: int = 50):
    from fba_tool.master_db import list_lingxing_sync_runs

    return {"items": list_lingxing_sync_runs(max(1, min(int(limit), 500)))}


@router.get("/api/lingxing/runs/{run_id}")
def api_lingxing_run_detail(run_id: int):
    run = get_lingxing_sync_run(int(run_id))
    if not run:
        raise HTTPException(status_code=404, detail="找不到该次同步记录")
    return {"run": run, "diffs": list_lingxing_sync_diffs(int(run_id))}


@router.get("/api/lingxing/sync-log")
def api_lingxing_sync_log(lines: int = 200):
    return {"lines": sched.read_log_tail(max(1, min(int(lines), 2000)))}
