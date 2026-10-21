"""历史任务:列表/保存/加载/重命名/删除。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from fba_tool.history_guard import safe_history_path
from fba_tool.session_store import (
    delete_history_task,
    list_history_tasks,
    load_history_payload,
    rename_history_task,
    save_history_payload,
    workflow_payload_has_data,
)
from schemas import TaskHistoryRenameRequest, TaskHistorySaveRequest

router = APIRouter()

_INVALID = {"code": "INVALID_TASK_ID", "message": "任务编号不合法"}


def _checked_task_id(task_id: str) -> str:
    try:
        return safe_history_path(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_INVALID) from exc


@router.get("/api/tasks/history")
def api_list_task_history(offset: int = 0, limit: int | None = None):
    tasks = list_history_tasks()
    return {
        "tasks": list_history_tasks(offset, limit),
        "total": len(tasks),
        "offset": offset,
        "limit": limit,
    }


@router.post("/api/tasks/history")
def api_save_task_history(body: TaskHistorySaveRequest):
    snapshot = dict(body.snapshot)
    if not workflow_payload_has_data(snapshot):
        raise HTTPException(status_code=400, detail="当前无有效任务数据，无需存档")
    if snapshot.get("task_id"):
        snapshot["task_id"] = _checked_task_id(str(snapshot.get("task_id")))
    try:
        task_id = save_history_payload(snapshot, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=_INVALID) from exc
    tasks = list_history_tasks()
    saved = next((t for t in tasks if t.get("id") == task_id), None)
    return {
        "ok": True,
        "task_id": task_id,
        "task_name": saved.get("name") if saved else snapshot.get("task_name"),
        "updated_at": saved.get("updated_at") if saved else None,
    }


@router.get("/api/tasks/history/{task_id}")
def api_load_task_history(task_id: str):
    task_id = _checked_task_id(task_id)
    data = load_history_payload(task_id)
    if not data:
        raise HTTPException(status_code=404, detail="历史任务不存在")
    return {"snapshot": data}


@router.patch("/api/tasks/history/{task_id}")
def api_rename_task_history(task_id: str, body: TaskHistoryRenameRequest):
    task_id = _checked_task_id(task_id)
    if not rename_history_task(task_id, body.name):
        raise HTTPException(status_code=404, detail="重命名失败")
    return {"ok": True, "task_id": task_id, "name": body.name.strip()}


@router.delete("/api/tasks/history/{task_id}")
def api_delete_task_history(task_id: str):
    task_id = _checked_task_id(task_id)
    if not delete_history_task(task_id):
        raise HTTPException(status_code=404, detail="删除失败")
    return {"ok": True, "task_id": task_id}
