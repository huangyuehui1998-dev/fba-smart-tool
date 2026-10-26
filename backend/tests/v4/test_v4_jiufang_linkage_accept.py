"""U5-M2-P4 九方黄字：合成账单≠Σ。≠九方联动已关，≠已改计费，≠Publish。

黄字只提示。逐箱计费重仍按实重/体积重取大，不把 Σ 改成账单。
第 13 批进位合计保持 1.30，不把第 15 批风格的 +1.00 并进总差。
第 15 批疑案不在这里判关闭。

夹具编号（spike / G2）：
- JF-REF-01：账单 101，5×20kg，61×46.5×37.5 → 黄字（gap=1.00）
- JF-REF-02：账单 100 → 无黄字
- JF-REF-03：账单 102 → 黄字
Accept 壳 §4 把 JF-REF-02/03 用来指第 13 批锚点和「不改计费」。
那两栏由本文件后两个测试守住，不另造一份账单夹具。
G3：对比页渲染 bill_warnings，见 frontend carton-compare 测试。
"""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from fba_tool.carton_math import (
    BILL_MISMATCH_WARNING,
    chargeable_kg,
    decompose,
    round_up_half_kg,
    summary_lines,
    bill_warnings,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "backend" / "tests" / "fixtures" / "synthetic" / "jiufang_linkage" / "cases.json"
DOC_SENTENCE = (
    "箱规对比页黄字表示账单≠Σ（与货代账单不一致，待确认），只待确认、不阻断；没有九方书面前不改计费。"
)


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    ad = tmp_path / "app_data"
    ad.mkdir()
    monkeypatch.setenv("FBA_APP_DATA_DIR", str(ad))
    monkeypatch.setenv("FBA_DISABLE_SCHEDULER", "1")
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    from fba_tool.master_db import init_master_db

    init_master_db()
    return ad


def _ticket(payload: dict, bill_kg: str) -> dict:
    dims = payload["dims_cm"]
    weight = payload["weight_kg"]
    rows = [{"weight_kg": weight, "dims": dims} for _ in range(int(payload["box_count"]))]
    return {"bill_kg": bill_kg, "rows": rows}


def test_g2_gap_one_kg_warns_and_equal_bill_does_not():
    payload = _payload()
    assert payload["warning"] == BILL_MISMATCH_WARNING == "与货代账单不一致，待确认"
    math = (ROOT / "backend" / "fba_tool" / "carton_math.py").read_text(encoding="utf-8")
    assert "货代账单计费重偏高，请核对" not in math
    one = chargeable_kg(payload["weight_kg"], payload["dims_cm"])
    assert one == Decimal("20.000")
    line = one * int(payload["box_count"])
    assert line == Decimal(payload["tool_sum_kg"])
    assert round_up_half_kg(line) == Decimal("100.0")

    for case in payload["cases"]:
        ticket = _ticket(payload, case["bill_kg"])
        notes = bill_warnings([ticket])
        parts = decompose([], [ticket])
        assert parts["carry"] == Decimal(case["gap_kg"]), case["id"]
        assert line == Decimal("100.000")
        if case["expect_warning"]:
            assert notes == [BILL_MISMATCH_WARNING], case["id"]
            assert "不一致" in notes[0] and "待确认" in notes[0]
        else:
            assert notes == [], case["id"]
        assert parts["carry"] != line


def test_batch13_anchors_do_not_absorb_plus_one():
    payload = _payload()
    anchor = payload["batch13_anchors"]
    tickets = []
    gaps = []
    for bill, line in zip(anchor["bills_kg"], anchor["line_sums_kg"]):
        ticket = {"bill_kg": bill, "rows": [{"weight_kg": line, "chargeable_kg": line}]}
        tickets.append(ticket)
        gaps.append(decompose([], [ticket])["carry"])
    assert gaps == [Decimal(item) for item in anchor["gaps_kg"]]
    assert sum(gaps, Decimal("0")) == Decimal(anchor["carry_total_kg"]) == Decimal("1.30")
    assert Decimal("1.00") not in gaps
    parts = decompose([], tickets)
    assert parts["carry"] == parts["total"] == Decimal("1.30")
    assert parts["total"] != Decimal("2.30")
    headline = summary_lines(parts, 5, [])["headline"]
    assert "+1.30" in headline
    assert "+2.30" not in headline
    assert bill_warnings(tickets) == []
    plus = decompose([], [_ticket(payload, "101")])
    assert plus["carry"] == Decimal("1.00")
    assert parts["total"] + plus["carry"] == Decimal("2.30")


def test_compare_warns_without_rewriting_chargeable(isolated):
    ad = isolated
    from fba_tool.carton_store import compare_carton, import_measurements, record_box_snapshot

    payload = _payload()
    dims = payload["dims_cm"]
    weight = payload["weight_kg"]
    for case in payload["cases"]:
        fba = f"FBATEST{case['id'].upper()}"
        boxes = []
        measured = []
        for index in range(1, int(payload["box_count"]) + 1):
            box_id = f"FBATESTU{case['id'][-2:]}{index:04d}"
            boxes.append({
                "fba_box_id": box_id,
                "box_no": index,
                "length_cm": dims[0],
                "width_cm": dims[1],
                "height_cm": dims[2],
                "gross_kg": weight,
                "sku_items": [{"sku": "TEST_JF_LINK"}],
            })
            measured.append({
                "kind": "box",
                "fba_id": fba,
                "fba_box_id": box_id,
                "sku": "TEST_JF_LINK",
                "length_cm": dims[0],
                "width_cm": dims[1],
                "height_cm": dims[2],
                "weight_kg": weight,
                "source_row": index,
            })
        record_box_snapshot(fba, "step4_validated", boxes)
        boxes_imported = import_measurements(
            measured,
            measured_by="forwarder_jiufang",
            source_file=f"{case['id']}-boxes.xlsx",
        )
        assert boxes_imported["inserted"] == 5, case["id"]
        import_measurements(
            [{
                "kind": "forwarder_bill",
                "fba_id": fba,
                "bill_chargeable_kg": case["bill_kg"],
                "forwarder": "jiufang",
            }],
            measured_by="forwarder_jiufang",
            source_file=f"{case['id']}-bill.xlsx",
        )
        report = compare_carton(fba)
        assert report["mode"] == "box", case["id"]
        assert len(report["rows"]) == 5
        assert all(row["计费重差"] == "0.00" for row in report["rows"])
        assert Decimal(str(report["summary"]["carry"])) == Decimal(case["gap_kg"])
        assert Decimal(str(report["summary"]["box_total"])) == Decimal("0.00")
        if case["expect_warning"]:
            assert report["bill_warnings"] == [BILL_MISMATCH_WARNING], case["id"]
        else:
            assert report["bill_warnings"] == [], case["id"]

    conn = sqlite3.connect(ad / "fba_master.db")
    try:
        bills = [Decimal(str(row[0])) for row in conn.execute("SELECT bill_chargeable_kg FROM forwarder_bill ORDER BY fba_id")]
        weights = [Decimal(str(row[0])) for row in conn.execute("SELECT weight_kg FROM carton_measurement")]
        stored_cw = [row[0] for row in conn.execute("SELECT chargeable_kg FROM carton_measurement")]
    finally:
        conn.close()
    assert bills == [Decimal(case["bill_kg"]) for case in payload["cases"]]
    assert weights == [Decimal(weight)] * (5 * len(payload["cases"]))
    assert stored_cw == [None] * len(weights)


def test_ticket_only_returns_bill_warnings_without_rewriting(isolated):
    ad = isolated
    from fba_tool.carton_store import compare_carton, import_measurements, record_box_snapshot

    fba = "FBATESTJFTICKET"
    record_box_snapshot(fba, "step4_validated", [{
        "fba_box_id": "FBATESTU000001",
        "box_no": 1,
        "length_cm": 40,
        "width_cm": 40,
        "height_cm": 40,
        "gross_kg": 10,
    }])
    import_measurements(
        [{"kind": "forwarder_bill", "fba_id": fba, "bill_chargeable_kg": "12.5", "forwarder": "jiufang"}],
        measured_by="forwarder_jiufang",
        source_file="ticket-bill.xlsx",
    )
    report = compare_carton(fba)
    assert report["mode"] == "ticket_only"
    assert report["message"] == "只有整票数据"
    assert "bill_warnings" in report
    assert report["bill_warnings"] == []
    assert report["summary"]["ticket_delta"] == 2.5

    empty = compare_carton("FBATESTNONE")
    assert empty["mode"] == "ticket_only"
    assert empty["bill_warnings"] == []

    conn = sqlite3.connect(ad / "fba_master.db")
    try:
        gross = conn.execute("SELECT gross_kg FROM shipment_box_snapshot").fetchone()[0]
        bill = conn.execute("SELECT bill_chargeable_kg FROM forwarder_bill").fetchone()[0]
    finally:
        conn.close()
    assert Decimal(str(gross)) == Decimal("10")
    assert Decimal(str(bill)) == Decimal("12.5")


def test_user_manual_states_yellow_does_not_change_billing():
    docs = (ROOT / "docs" / "使用说明.md").read_text(encoding="utf-8")
    portable = (ROOT / "packaging" / "使用说明.txt").read_text(encoding="utf-8")
    assert docs.count(DOC_SENTENCE) == 1
    assert portable.count(DOC_SENTENCE) == 1
    assert "账单≠Σ" in DOC_SENTENCE
    assert "不改计费" in DOC_SENTENCE
