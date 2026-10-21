"""R12-12：历史路径穿越统一 400，合法编号仍可读写。"""
from __future__ import annotations

from urllib.parse import quote

from fastapi.testclient import TestClient

from fba_tool.session_store import save_history_payload
from main import app

_EVIL = [
    "../../TEST_evil",
    "TEST_ok/../../x",
    "..\\..\\x",
    "%2e%2e/x",
    "a%2F..%2F..%2Fx",
]


def _encode_task_id(raw: str) -> str:
    """斜杠和反斜杠编码，已有百分号再编码一层，点号保留。"""
    return "".join("%25" if ch == "%" else quote(ch, safe=".") for ch in raw)


def _detail(response):
    body = response.json()
    detail = body.get("detail", body)
    return detail if isinstance(detail, dict) else {}


def test_traversal_ids_are_400_on_every_method():
    client = TestClient(app)
    snapshot = {"input_df": [{"SKU简称": "TEST_A"}], "task_id": ""}
    for raw in _EVIL:
        encoded = _encode_task_id(raw)
        posted = client.post("/api/tasks/history", json={"snapshot": {**snapshot, "task_id": raw}})
        assert posted.status_code == 400, posted.text
        assert _detail(posted).get("code") == "INVALID_TASK_ID"
        for method in ("get", "patch", "delete"):
            kwargs = {"json": {"name": "TEST_NAME"}} if method == "patch" else {}
            response = getattr(client, method)(f"/api/tasks/history/{encoded}", **kwargs)
            assert response.status_code == 400, (method, raw, response.status_code, response.text)
            assert _detail(response).get("code") == "INVALID_TASK_ID"


def test_history_routes_still_work_and_download_names_are_checked():
    client = TestClient(app)
    listed = client.get("/api/tasks/history")
    assert listed.status_code == 200
    files = client.get("/api/history/files")
    assert files.status_code == 200

    task_id = save_history_payload({"task_id": "Task-20260907-1344", "input_df": [{"SKU简称": "TEST_A"}]})
    loaded = client.get(f"/api/tasks/history/{task_id}")
    assert loaded.status_code == 200
    missing = client.delete("/api/tasks/history/NOPE_123")
    assert missing.status_code == 404

    ok = client.get("/api/history/files/download", params={"kind": "csv", "name": "测试装箱单_A.csv"})
    assert ok.status_code == 200
    absent = client.get("/api/history/files/download", params={"kind": "csv", "name": "NO_SUCH_FILE.csv"})
    assert absent.status_code == 404
    for name in ("../x", "..%2Fx", "%252e%252e%252fx", "a\\..\\x"):
        blocked = client.get("/api/history/files/download", params={"kind": "csv", "name": name})
        assert blocked.status_code == 400, (name, blocked.status_code, blocked.text)
        assert _detail(blocked).get("code") == "INVALID_FILE_NAME"
