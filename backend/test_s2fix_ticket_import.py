"""S2-fix 第1项：票级数据导入器（腾讯表格 / 运费测算表 / 九方单箱数据）→ shipment_ticket。

方案 3.2 验收第 3 条：腾讯表格和运费测算表导入后，第 14 批 5 票的毛重和 T3:T7 一致。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fba_tool.master_db import init_master_db
from tests._realdata import requires_realdata
from fba_tool.ticket_import import (
    apply_ticket_import,
    detect_ticket_source,
    get_ticket,
    list_tickets,
    parse_ticket_file,
    preview_ticket_import,
    set_ticket_fields,
)

FX = Path(__file__).parent / "tests" / "fixtures" / "tickets"
TENCENT = FX / "tencent_b14.xlsx"
FREIGHT = FX / "freight_records.xlsx"
JIUFANG = FX / "jiufang_LCL2609EZGXA.xlsx"
pytestmark = requires_realdata(TENCENT, FREIGHT, JIUFANG)

B14_GROSS = {  # 腾讯表格文档.xlsx Sheet1!T3:T7
    "FBA19RJCXY6X": 267.2, "FBA19RJH13MS": 115.2, "FBA19RJD3V7G": 228.0, "FBA19RJCV4RX": 200.4, "FBA19RJCC1BM": 191.2,
}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    ad = tmp_path / "app_data"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    init_master_db()


def _imp(p: Path):
    return apply_ticket_import(p.read_bytes(), p.name)


def test_detect_sources():
    assert detect_ticket_source(TENCENT.read_bytes(), TENCENT.name) == "tencent"
    assert detect_ticket_source(FREIGHT.read_bytes(), FREIGHT.name) == "freight"
    assert detect_ticket_source(JIUFANG.read_bytes(), JIUFANG.name) == "jiufang"


def test_tencent_parse_b14():
    rows, issues = parse_ticket_file(TENCENT.read_bytes(), TENCENT.name)
    by = {r["fba_id"]: r for r in rows}
    assert set(by) == set(B14_GROSS)
    t = by["FBA19RJCXY6X"]
    assert t["order_no"] == "JUS14DD28" and t["warehouse_code"] == "TEB9" and t["box_count"] == 28
    assert t["batch"] == "14" and t["ticket_no"] == "第一票" and t["region"] == "美东"
    assert t["chargeable_kg"] == 373.5 and t["total_freight"] == 622.84


def test_acceptance_b14_gross_matches_T3_T7_after_tencent_and_freight():
    _imp(TENCENT)
    _imp(FREIGHT)
    got = {t["fba_id"]: t["gross_kg"] for t in list_tickets(batch="14")}
    assert got == B14_GROSS
    t = get_ticket("FBA19RJCXY6X")
    assert t["forwarder"] == "九方"            # 运费测算表补的字段
    assert t["field_sources"]["gross_kg"] == "tencent"
    assert t["field_sources"]["forwarder"] == "freight"


def test_freight_dates_and_priority():
    _imp(FREIGHT)
    t = get_ticket("FBA196QL4HP5")
    assert t["etd"] == "2026-02-04" and t["eta_expected"] == "2026-03-10"
    assert t["delivered_at"] == "2026-03-22" and t["amazon_received_at"] == "2026-03-22"
    # 合同协议号列里不是订单号（“买单出口”）时不写入，给提示
    assert not t["order_no"]
    _, issues = parse_ticket_file(FREIGHT.read_bytes(), FREIGHT.name)
    assert any(i["field"] == "order_no" for i in issues)
    # 运费测算表的计费重不覆盖腾讯表格已有值
    _imp(TENCENT)
    assert get_ticket("FBA19RJCXY6X")["chargeable_kg"] == 373.5


def test_jiufang_boxes_keep_tencent_gross():
    _imp(JIUFANG)
    tickets = list_tickets()
    assert tickets and all(t["lcl_no"] == "LCL2609EZGXA" for t in tickets)
    one = tickets[0]
    assert one["boxes"] and {"box_no", "weight", "length", "width", "height"} <= set(one["boxes"][0])
    assert one["field_sources"]["gross_kg"] == "jiufang"
    set_ticket_fields(one["fba_id"], {"gross_kg": 100.0}, "tencent")
    _imp(JIUFANG)  # 再导九方不覆盖腾讯表格的毛重
    assert get_ticket(one["fba_id"])["gross_kg"] == 100.0


def test_preview_does_not_write_and_second_import_zero_diff():
    pv = preview_ticket_import(TENCENT.read_bytes(), TENCENT.name)
    assert pv["summary"]["new"] == 5 and list_tickets() == []
    _imp(TENCENT)
    pv2 = preview_ticket_import(TENCENT.read_bytes(), TENCENT.name)
    assert pv2["summary"]["new"] == 0 and pv2["summary"]["changed"] == 0


def test_manual_wins_and_freight_not_in_customs():
    _imp(TENCENT)
    set_ticket_fields("FBA19RJCXY6X", {"gross_kg": 270.0}, "manual")
    _imp(TENCENT)
    assert get_ticket("FBA19RJCXY6X")["gross_kg"] == 270.0
    # 运费只作参考：报关数据没有从 shipment_ticket 取运费的字段
    from fba_tool.customs_package import CustomsPackageData
    assert CustomsPackageData().freight == ""


def test_api_preview_apply_list():
    from main import app

    c = TestClient(app)
    with TENCENT.open("rb") as f:
        r = c.post("/api/tickets/import/preview", files={"file": (TENCENT.name, f)})
    assert r.status_code == 200 and r.json()["source"] == "tencent"
    with TENCENT.open("rb") as f:
        assert c.post("/api/tickets/import/apply", files={"file": (TENCENT.name, f)}).status_code == 200
    items = c.get("/api/tickets", params={"batch": "14"}).json()["items"]
    assert len(items) == 5
    bad = c.post("/api/tickets/import/preview", files={"file": ("x.xlsx", b"nope")})
    assert bad.status_code == 422
