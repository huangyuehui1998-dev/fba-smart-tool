"""Univer 快照与回写。货代 xlsx 只在后端用 openpyxl 转换。"""
from __future__ import annotations

import base64
import json
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from fba_tool.job_runner import RUNNER, public_job
from fba_tool.univer_apply import ApplyRejected

router = APIRouter()

SYNC_WAIT_SECONDS = 2.0
ASYNC_ROW_THRESHOLD = 5000


def _template_bytes(forwarder_id: str) -> bytes:
    from fba_tool.forwarder_registry import get_template_bytes

    return get_template_bytes(forwarder_id)


def _convert(data: bytes, clamp: bool, job: Any) -> dict:
    from fba_tool.univer_snapshot import workbook_to_snapshot

    def progress(pct: int) -> None:
        job.progress = max(0, min(99, int(pct)))

    return workbook_to_snapshot(data, clamp=clamp, progress=progress, cancel_event=job.cancel_event)


@router.post("/api/univer/snapshot")
async def api_univer_snapshot(
    request: Request,
    clamp: bool = Query(True),
    forwarder_id: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    data = await _read_upload(request, file, forwarder_id)
    return _snapshot_response(data, clamp)


@router.post("/api/univer/apply")
async def api_univer_apply(request: Request):
    data, snapshot = await _read_apply(request)
    from fba_tool.univer_apply import apply_snapshot_values

    try:
        out = apply_snapshot_values(data, snapshot)
    except ApplyRejected as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "cells": exc.cells, "message": exc.message}) from exc
    return Response(
        content=out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=invoice.xlsx"},
    )


@router.post("/api/jobs")
async def api_enqueue_job(request: Request):
    body = await request.json()
    kind = str(body.get("type") or "")
    if kind != "univer_snapshot":
        raise HTTPException(status_code=400, detail="未知任务类型")
    forwarder_id = body.get("forwarder_id")
    if not forwarder_id:
        raise HTTPException(status_code=400, detail="需要 forwarder_id")
    data = _template_bytes(str(forwarder_id))
    clamp = bool(body.get("clamp", True))
    job, _done = RUNNER.submit(lambda job: _convert(data, clamp, job), sync_timeout=0)
    return JSONResponse(status_code=202, content=public_job(job, include_result=False))


@router.get("/api/jobs/{job_id}")
def api_get_job(job_id: str):
    job = RUNNER.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到任务")
    return public_job(job)


@router.post("/api/jobs/{job_id}/cancel")
def api_cancel_job(job_id: str):
    job = RUNNER.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到任务")
    if job.status in {"queued", "running"}:
        job.status = "cancelled"
    return public_job(job, include_result=False)


def _snapshot_response(data: bytes, clamp: bool):
    from fba_tool.univer_snapshot import estimate_used_rows

    used = estimate_used_rows(data)
    timeout = 0.0 if used > ASYNC_ROW_THRESHOLD else SYNC_WAIT_SECONDS
    job, finished = RUNNER.submit(lambda current: _convert(data, clamp, current), sync_timeout=timeout)
    if finished and job.status == "done":
        result = job.result or {}
        return {"snapshot": result.get("snapshot"), "meta": {**(result.get("meta") or {}), "used_rows_estimate": used}}
    if finished and job.status == "failed":
        raise HTTPException(status_code=500, detail=job.error or "转换失败")
    if job.status == "cancelled":
        return JSONResponse(status_code=202, content=public_job(job, include_result=False))
    return JSONResponse(status_code=202, content=public_job(job, include_result=False))


async def _read_upload(request: Request, file: Optional[UploadFile], forwarder_id: Optional[str]) -> bytes:
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        body = await request.json()
        if body.get("file_base64"):
            return base64.b64decode(body["file_base64"])
        if body.get("forwarder_id"):
            return _template_bytes(str(body["forwarder_id"]))
        raise HTTPException(status_code=400, detail="需要 file 或 forwarder_id")
    if file is not None and file.filename:
        payload = await file.read()
        if payload:
            return payload
    if forwarder_id:
        return _template_bytes(forwarder_id)
    raise HTTPException(status_code=400, detail="需要 file 或 forwarder_id")


async def _read_apply(request: Request) -> tuple[bytes, dict]:
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        body = await request.json()
        snapshot = body.get("snapshot")
        if not isinstance(snapshot, dict):
            raise HTTPException(status_code=400, detail="snapshot 必须是对象")
        if body.get("file_base64"):
            return base64.b64decode(body["file_base64"]), snapshot
        if body.get("forwarder_id"):
            return _template_bytes(str(body["forwarder_id"])), snapshot
        raise HTTPException(status_code=400, detail="需要 file_base64 或 forwarder_id")
    form = await request.form()
    raw = form.get("snapshot")
    if not raw:
        raise HTTPException(status_code=400, detail="缺少 snapshot")
    snapshot = json.loads(str(raw))
    upload = form.get("file")
    if upload is not None and getattr(upload, "filename", None):
        return await upload.read(), snapshot
    forwarder_id = form.get("forwarder_id")
    if not forwarder_id:
        raise HTTPException(status_code=400, detail="需要 file 或 forwarder_id")
    return _template_bytes(str(forwarder_id)), snapshot
