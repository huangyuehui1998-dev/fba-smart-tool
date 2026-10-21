"""R12-07：口径 B，认单箱实重，纯数字外箱号，表尾不 500。"""
from __future__ import annotations

import io
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from fba_tool.carton_math import (
    chargeable_kg_rounded,
    lb_to_kg_exact,
    round_up_half_kg,
    volumetric_kg,
)
from fba_tool.measurement_adapters import ParseError, detect_adapter


def _book(headers, rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_rounding_b_synthetic_cases():
    assert volumetric_kg(47, 46.5, 44) == Decimal("16.03")
    assert volumetric_kg(Decimal("45.01"), Decimal("45.01"), Decimal("41")) == Decimal("13.84")
    assert chargeable_kg_rounded("20.004", volumetric_kg(61, 46.5, 37.5)) == Decimal("20.00")
    assert chargeable_kg_rounded("20.005", Decimal("17.73")) == Decimal("20.01")
    assert chargeable_kg_rounded(lb_to_kg_exact("16.53"), volumetric_kg(30, 30, 40)) == Decimal("7.50")
    assert round_up_half_kg("332.48") == Decimal("332.5")
    assert round_up_half_kg("332.50") == Decimal("332.5")
    assert round_up_half_kg("332.5033125") == Decimal("333.0")
    assert not hasattr(__import__("fba_tool.carton_math", fromlist=["x"]), "published_batch13_identity")


def test_numeric_box_ids_and_footer_text(monkeypatch, tmp_path):
    headers = ["序号", "运单号", "外箱号", "单箱实重", "长", "宽", "高", "单箱材重", "计费重"]
    rows = [
        [1, "LCL1", 1.0, 20.004, 61, 46.5, 37.5, 17.73, 20],
        [2, "LCL1", "12", 9.9, 40, 40, 40, 10.67, 10.67],
        [3, "LCL1", "FBATESTU000001", "表尾", 1, 1, 1, None, None],
        [None, None, None, None, None, None, "入库计费重", 100, None],
        [None, None, None, None, None, None, None, None, None],
    ]
    blob = _book(headers, rows)
    parsed = detect_adapter("九方.xlsx", blob).parse(blob)
    boxes = [row for row in parsed if row["kind"] == "box"]
    assert [row["fba_box_id"] for row in boxes] == ["1", "12", ]
    assert all(row["match_status"] == "invalid_id" for row in boxes)
    assert any(row["kind"] == "issue" for row in parsed)
    bill = next(row for row in parsed if row["kind"] == "forwarder_bill")
    assert bill["waybill"] == "LCL1"
    assert bill["bill_chargeable_kg"] == 100

    monkeypatch.setenv("FBA_APP_DATA_DIR", str(tmp_path))
    from fba_tool.master_db import init_master_db

    init_master_db()
    from main import app

    client = TestClient(app)
    first = client.post(
        "/api/measurements/import/apply",
        files={"file": ("九方.xlsx", blob, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert first.status_code == 200, first.text
    assert first.json()["issues"]
    second = client.post(
        "/api/measurements/import/apply",
        files={"file": ("九方.xlsx", blob, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert second.status_code == 200
    import sqlite3

    conn = sqlite3.connect(tmp_path / "fba_master.db")
    try:
        bills = conn.execute("SELECT COUNT(*) FROM forwarder_bill").fetchone()[0]
        boxes_n = conn.execute("SELECT COUNT(*) FROM carton_measurement").fetchone()[0]
    finally:
        conn.close()
    assert bills == 1
    assert boxes_n == 2


def test_missing_weight_column_is_422(monkeypatch, tmp_path):
    blob = _book(["外箱号", "长", "宽", "高"], [["FBATESTU000001", 40, 40, 40]])
    with pytest.raises(ParseError, match="单箱实重"):
        detect_adapter("九方.xlsx", blob).parse(blob)
    monkeypatch.setenv("FBA_APP_DATA_DIR", str(tmp_path))
    from fba_tool.master_db import init_master_db

    init_master_db()
    from main import app

    client = TestClient(app)
    response = client.post(
        "/api/measurements/import/apply",
        files={"file": ("九方.xlsx", blob, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 422
    assert "单箱实重" in response.text
