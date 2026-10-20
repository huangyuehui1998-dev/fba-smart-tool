"""S3-fix2：多票合并净重、最大余数法分摊、0 重量行提示、货代毛重容差。"""
from __future__ import annotations

from decimal import Decimal

import pytest

from fba_tool import customs_package as cp
from fba_tool.customs_package import _allocate_cents, build_customs_from_tickets, consistency_checks
from fba_tool.warehouse_db import get_default_rule_profile, update_rule_profile

PROFILE = {"id": "t", "name": "测试公司", "credit_code": "X", "signed_at": "武汉", "domestic_source": "武汉"}
PET = {"chinese_name": "宠物垫", "hs_code": "6307909000", "unit": "包", "brand": "DemoBrand", "category": "pet"}
DOG = {"chinese_name": "车载狗栏", "hs_code": "7326909000", "unit": "个", "brand": "DemoBrand", "category": "pet"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    ad = tmp_path / "ad"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    from fba_tool.master_db import init_master_db

    init_master_db()
    monkeypatch.setattr(cp, "_catalog_hints", lambda sku: {})


def test_mixed_plus_single_ticket_net_summed_per_name():
    # 票1 混装：2 箱 10kg，宠物垫 1 件 + 狗栏 1 件 → 毛 10、净 9.6，各分 5.0/4.8
    mixed = {"shipment_id": "F1", "warehouse": "SBD1", "boxes": [5, 5],
             "lines": [dict(PET, sku="A", qty=1, unit_price=10), dict(DOG, sku="B", qty=1, unit_price=20)]}
    # 票2 单品名：3 箱 18kg 宠物垫 → 净 18 − 0.6 = 17.4
    single = {"shipment_id": "F2", "warehouse": "LAX9", "boxes": [6, 6, 6], "lines": [dict(PET, sku="A", qty=3, unit_price=10)]}
    d = build_customs_from_tickets([mixed, single], PROFILE, order_no="JUS1HB5")
    pet = next(l for l in d.lines if l.chinese_name == "宠物垫")
    assert pet.net_kg == 22.2 and pet.gross_kg == 23.0
    assert d.total_net_kg == 27.0
    assert sum(Decimal(str(l.net_kg)) for l in d.lines) == Decimal("27.0")
    assert consistency_checks(d) == []


@pytest.mark.parametrize("total,weights,expect", [
    (Decimal("0.02"), [1, 1, 1, 1], [Decimal("0.01"), Decimal("0.01"), Decimal("0"), Decimal("0")]),
    (Decimal("30.01"), [1, 2], [Decimal("10.00"), Decimal("20.01")]),
    (Decimal("10"), [1, 1, 1], [Decimal("3.34"), Decimal("3.33"), Decimal("3.33")]),
])
def test_largest_remainder(total, weights, expect):
    got = _allocate_cents(total, [Decimal(w) for w in weights])
    assert got == expect and sum(got) == total and all(g >= 0 for g in got)


def test_four_names_net_002_no_negative_and_zero_line_warned():
    names = [dict(PET, chinese_name=f"品名{i}", sku=f"S{i}", qty=1, unit_price=1) for i in range(4)]
    t = {"shipment_id": "F1", "warehouse": "SBD1", "boxes": [0.22], "lines": names}
    d = build_customs_from_tickets([t], PROFILE, order_no="JUS1DD1")
    assert d.total_net_kg == 0.02
    nets = [Decimal(str(l.net_kg)) for l in d.lines]
    assert all(n >= 0 for n in nets) and sum(nets) == Decimal("0.02")
    w = [x for x in d.warnings if x["code"] == "zero_weight_line"]
    assert w and "品名2" in w[0]["message"] and "品名3" in w[0]["message"]


def test_forwarder_tolerance_default_and_configurable():
    assert get_default_rule_profile()["forwarder_gross_tolerance_kg"] == 0.5
    t = {"shipment_id": "F1", "warehouse": "SBD1", "boxes": [8.2] * 28, "gross_kg": 230.0, "lines": [dict(PET, sku="A", qty=1, unit_price=1)]}
    d = build_customs_from_tickets([t], PROFILE, order_no="JUS1DD28")
    assert "forwarder_gross_mismatch" not in {x["code"] for x in d.warnings}  # 差 0.4 ≤ 0.5
    update_rule_profile({"forwarder_gross_tolerance_kg": 0.1})
    d = build_customs_from_tickets([t], PROFILE, order_no="JUS1DD28")
    assert "forwarder_gross_mismatch" in {x["code"] for x in d.warnings}


def test_tolerance_not_negative():
    with pytest.raises(ValueError):
        update_rule_profile({"forwarder_gross_tolerance_kg": -1})


def test_old_db_gets_tolerance_column():
    import sqlite3

    from fba_tool.master_schema import ensure_v3

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE customs_rule_profile (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, net_weight_mode TEXT,"
                 " net_minus_per_box REAL, net_ratio REAL, total_price_rule TEXT, loading_port TEXT, entrust_valid_until_rule TEXT,"
                 " exemption_nature TEXT, transport_mode TEXT, fill_freight INTEGER, fill_export_declare_date INTEGER,"
                 " is_default INTEGER, updated_at TEXT NOT NULL)")
    ensure_v3(conn)
    assert conn.execute("SELECT forwarder_gross_tolerance_kg FROM customs_rule_profile").fetchone()[0] == 0.5
