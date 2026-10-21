"""N1：运单号写入 fba_id/waybill，进位按票匹配，对不上的账单不整票加进去。"""
from __future__ import annotations

import io
import sqlite3
from decimal import Decimal

import pytest
from openpyxl import Workbook


TAILS = [Decimal("509"), Decimal("332.5"), Decimal("604"), Decimal("584"), Decimal("517")]
SUMS = [Decimal("508.70"), Decimal("332.48"), Decimal("603.62"), Decimal("583.76"), Decimal("516.64")]


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    ad = tmp_path / "app_data"
    ad.mkdir()
    monkeypatch.setenv("FBA_APP_DATA_DIR", str(ad))
    monkeypatch.setenv("FBA_DISABLE_SCHEDULER", "1")
    monkeypatch.delenv("FBA_SKIP_MIGRATION", raising=False)
    from fba_tool.master_db import init_master_db

    init_master_db()
    return ad


def _book(waybill: str, box_id: str, weight: Decimal, bill: Decimal) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["外箱号", "运单号", "单箱实重", "长", "宽", "高"])
    ws.append([box_id, waybill, str(weight), 10, 10, 10])
    ws.append(["入库计费重", str(bill)])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_waybill_import_matches_carry_and_flags_unmatched_bill(isolated):
    from fastapi.testclient import TestClient

    from fba_tool.db_migrations import ensure_measurement_waybill
    from main import create_app

    client = TestClient(create_app())
    for index, (weight, bill) in enumerate(zip(SUMS, TAILS), start=1):
        blob = _book(f"WBTEST{index}", f"FBATESTU00000{index}", weight, bill)
        response = client.post(
            "/api/measurements/import/apply",
            files={"file": (f"九方实测-{index}.xlsx", blob, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert response.status_code == 200, response.text

    conn = sqlite3.connect(isolated / "fba_master.db")
    try:
        stored = conn.execute(
            "SELECT fba_id, waybill FROM carton_measurement ORDER BY waybill"
        ).fetchall()
    finally:
        conn.close()
    assert stored == [(f"WBTEST{index}", f"WBTEST{index}") for index in range(1, 6)]

    for index, weight in enumerate(SUMS, start=1):
        posted = client.post(
            f"/api/shipments/FBATESTSHIP{index}/box-snapshot",
            json={
                "stage": "step4_validated",
                "batch": "13",
                "boxes": [{
                    "fba_box_id": f"FBATESTU00000{index}",
                    "box_no": 1,
                    "length_cm": 10,
                    "width_cm": 10,
                    "height_cm": 10,
                    "gross_kg": float(weight),
                }],
            },
        )
        assert posted.status_code == 200, posted.text

    report = client.get("/api/carton-compare", params={"batch": "13"}).json()
    assert report["mode"] == "box"
    assert Decimal(str(report["summary"]["carry"])) == Decimal("1.30")
    assert Decimal(str(report["summary"]["total"])) == Decimal("1.30")
    assert report["summary"]["carry_scope"] == "按票匹配"

    from fba_tool.carton_store import import_measurements

    import_measurements(
        [{
            "kind": "forwarder_bill",
            "fba_id": "WBTEST9",
            "bill_chargeable_kg": 100,
            "forwarder": "jiufang",
        }],
        measured_by="forwarder_jiufang",
        source_file="extra.xlsx",
    )
    again = client.get("/api/carton-compare", params={"batch": "13"}).json()
    assert Decimal(str(again["summary"]["carry"])) == Decimal("1.30")
    flagged = [row for row in again["quality"] if row.get("match_status") == "账单无对应过机行"]
    assert flagged and flagged[0]["fba_box_id"] == "WBTEST9"
    assert "WBTEST9" in again["summary"]["unmatched_bills"]

    conn = sqlite3.connect(isolated / "fba_master.db")
    try:
        conn.execute(
            """INSERT INTO carton_measurement
               (fba_id, waybill, fba_box_id, raw_json, measured_by, source_file, content_hash)
               VALUES ('', NULL, 'FBATESTU000099', '{"waybill":"WBTESTBACK"}', 'forwarder_jiufang', 'old.xlsx', 'hashback')"""
        )
        conn.commit()
        ensure_measurement_waybill(conn)
        conn.commit()
        healed = conn.execute(
            "SELECT fba_id, waybill FROM carton_measurement WHERE fba_box_id=?",
            ("FBATESTU000099",),
        ).fetchone()
    finally:
        conn.close()
    assert healed == ("WBTESTBACK", "WBTESTBACK")
