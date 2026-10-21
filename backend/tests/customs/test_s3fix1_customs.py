"""S3-fix1：重量为 0 拦截、货代毛重差异提示（v5 Q2）、多品名混装分摊规则。"""
from __future__ import annotations

from decimal import Decimal

import pytest

from fba_tool import customs_package as cp
from fba_tool.customs_export import CustomsExportBlocked, export_blockers
from fba_tool.customs_package import build_customs_from_tickets, consistency_checks

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


def _codes(x):
    return {i["code"] for i in x}


# ---------- 1. 毛重 / 净重 > 0 ----------
def test_zero_gross_blocks_when_pieces_positive():
    t = {"shipment_id": "F1", "warehouse": "SBD1", "box_count": 5, "gross_kg": 0, "lines": [dict(PET, sku="A", qty=5, unit_price=1)]}
    d = build_customs_from_tickets([t], PROFILE, order_no="JUS1DD5")
    assert {"gross_not_positive", "net_not_positive"} <= _codes(consistency_checks(d))
    assert any("毛重" in b for b in export_blockers(d))


def test_net_zero_alone_blocks():
    t = {"shipment_id": "F1", "warehouse": "SBD1", "boxes": [10], "lines": [dict(PET, sku="A", qty=5, unit_price=1)]}
    d = build_customs_from_tickets([t], PROFILE, order_no="JUS1DD1")
    d.total_net_kg = 0
    assert "net_not_positive" in _codes(consistency_checks(d))


def test_exempt_codes_only_for_tests():
    t = {"shipment_id": "F1", "warehouse": "SBD1", "box_count": 5, "gross_kg": 0, "lines": [dict(PET, sku="A", qty=5, unit_price=1)]}
    d = build_customs_from_tickets([t], PROFILE, order_no="JUS1DD5")
    assert export_blockers(d, exempt_codes={"gross_not_positive", "net_not_positive"}) == []


# ---------- 2. 货代毛重 vs Σ单箱重（v5 Q2：只提示） ----------
def test_forwarder_gross_mismatch_warns():
    t = {"shipment_id": "FBA19RJCXY6X", "warehouse": "TEB9", "boxes": [8.2] * 28, "gross_kg": 267.2,
         "lines": [dict(PET, sku="A", qty=168, unit_price=39.99)]}
    d = build_customs_from_tickets([t], PROFILE, order_no="JUS14DD28")
    w = [x for x in d.warnings if x["code"] == "forwarder_gross_mismatch"]
    assert w and "229.6" in w[0]["message"] and "267.2" in w[0]["message"]
    assert d.total_gross_kg == 229.6  # 仍按 Σ单箱重
    assert "forwarder_gross_mismatch" not in _codes(d.blocking)


def test_forwarder_gross_equal_no_warning():
    t = {"shipment_id": "F1", "warehouse": "SBD1", "boxes": [8.2] * 28, "gross_kg": 229.6, "lines": [dict(PET, sku="A", qty=1, unit_price=1)]}
    d = build_customs_from_tickets([t], PROFILE, order_no="JUS1DD28")
    assert "forwarder_gross_mismatch" not in _codes(d.warnings)


# ---------- 5. 多品名混装、行上没给箱数：箱数记第一行，毛重/净重按件数分摊，各行合计 = 总数 ----------
def test_mixed_multi_name_allocation():
    t = {"shipment_id": "F1", "warehouse": "SBD1", "boxes": [10, 10, 10.01],
         "lines": [dict(PET, sku="A", qty=1, unit_price=10), dict(DOG, sku="B", qty=2, unit_price=20)]}
    d = build_customs_from_tickets([t], PROFILE, order_no="JUS1DD3")
    a, b = d.lines
    assert (a.box_count, b.box_count) == (3, 0)
    assert a.gross_kg == 10.0 and b.gross_kg == 20.01  # 30.01 × 1/3 → 10.00，余数给最后一行
    assert Decimal(str(a.gross_kg)) + Decimal(str(b.gross_kg)) == Decimal(str(d.total_gross_kg))
    assert Decimal(str(a.net_kg)) + Decimal(str(b.net_kg)) == Decimal(str(d.total_net_kg)) == Decimal("29.41")
    assert consistency_checks(d) == []


def test_allocation_sum_checked():
    t = {"shipment_id": "F1", "warehouse": "SBD1", "boxes": [10, 10],
         "lines": [dict(PET, sku="A", qty=1, unit_price=10), dict(DOG, sku="B", qty=1, unit_price=20)]}
    d = build_customs_from_tickets([t], PROFILE, order_no="JUS1DD2")
    d.lines[1].gross_kg += 1
    assert "lines_gross_mismatch" in _codes(consistency_checks(d))
