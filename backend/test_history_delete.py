"""P1-8：删除不存在的历史任务返回 404。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from fba_tool.session_store import delete_history_task, save_history_payload
from main import app


def test_delete_missing_history_id_returns_404():
    client = TestClient(app)
    missing = client.delete("/api/tasks/history/TEST_MISSING_HISTORY")
    assert missing.status_code == 404

    task_id = save_history_payload({"task_id": "TESTDELHIST1", "rows": [{"sku": "TEST_A"}]})
    gone = client.delete(f"/api/tasks/history/{task_id}")
    assert gone.status_code == 200
    again = client.delete(f"/api/tasks/history/{task_id}")
    assert again.status_code == 404
    assert delete_history_task(task_id) is False
