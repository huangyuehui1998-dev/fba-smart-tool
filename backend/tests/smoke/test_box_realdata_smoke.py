"""R12-03：箱侧真实数据冒烟。没有 realdata 时跳过，不把未核实的数字写成通过。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.smoke.reference import available

pytestmark = pytest.mark.realdata_smoke

CASES = ("S-01", "S-02", "S-03", "S-04", "S-05", "S-06", "S-07")


def _write(items: list[dict]) -> None:
    dest = os.environ.get("SMOKE_REPORT_PATH")
    if not dest:
        return
    Path(dest).write_text(
        json.dumps(
            {
                "items": items,
                "note": "pending_verification 的红绿结果、以及第 15 批账单与逐箱合计的差额，都不作为断言。",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_box_realdata_smoke():
    if not available():
        _write([{"id": case, "status": "skipped", "reason": "realdata 不在本环境"} for case in CASES])
        pytest.skip("需要 box realdata")
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/fx-rates")
    assert response.status_code < 500
    _write([{"id": case, "status": "present", "http": response.status_code} for case in CASES])
