"""历史任务:列表/保存/加载/重命名/删除。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

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
    task_id = save_history_payload(snapshot, name=body.name)
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
    data = load_history_payload(task_id)
    if not data:
        raise HTTPException(status_code=404, detail="历史任务不存在")
    return {"snapshot": data}


@router.patch("/api/tasks/history/{task_id}")
def api_rename_task_history(task_id: str, body: TaskHistoryRenameRequest):
    if not rename_history_task(task_id, body.name):
        raise HTTPException(status_code=404, detail="重命名失败")
    return {"ok": True, "task_id": task_id, "name": body.name.strip()}


@router.delete("/api/tasks/history/{task_id}")
def api_delete_task_history(task_id: str):
    if not delete_history_task(task_id):
        raise HTTPException(status_code=404, detail="删除失败")
    return {"ok": True, "task_id": task_id}
