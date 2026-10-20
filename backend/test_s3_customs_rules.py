"""S3-1 报关规则引擎（方案 v8 §3.6、§5-7）：净重规则统一到 customs_rule_profile、Decimal、按票装配。"""
from __future__ import annotations

from decimal import Decimal

import pytest

from fba_tool import customs_package as cp
from fba_tool.customs_package import build_customs_from_tickets, compute_net_weight
from fba_tool.warehouse_db import get_default_rule_profile, update_rule_profile

PROFILE = {"id": "t", "name": "测试公司", "credit_code": "X", "signed_at": "武汉", "domestic_source": "武汉"}
PET = {"chinese_name": "宠物垫", "hs_code": "6307909000", "unit": "包", "brand": "DemoBrand", "category": "pet"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    ad = tmp_path / "ad"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    from fba_tool.master_db import init_master_db

    init_master_db()
    monkeypatch.setattr(cp, "_catalog_hints", lambda sku: {})


def _ticket(boxes, lines, sid="FBA1", wh="SBD1"):
    return {"shipment_id": sid, "warehouse": wh, "boxes": boxes, "lines": lines}


def test_net_weight_default_minus_per_box_from_profile():
    assert get_default_rule_profile()["net_weight_mode"] == "minus_per_box"
    assert compute_net_weight(Decimal("173.50"), 21) == 169.30


def test_net_weight_follows_profile_change():
    update_rule_profile({"net_minus_per_box": 0.5})
    assert compute_net_weight(100, 10) == 95.0
    update_rule_profile({"net_weight_mode": "ratio", "net_ratio": 0.95})
    assert compute_net_weight(173.5, 21) == 164.83  # 164.825 HALF_UP


def test_net_weight_mode_validated():
    with pytest.raises(ValueError):
        update_rule_profile({"net_weight_mode": "abc"})
    with pytest.raises(ValueError):
        update_rule_profile({"net_weight_mode": "ratio", "net_ratio": None})


def test_user_settings_no_longer_affect_net(monkeypatch):
    monkeypatch.setattr(cp, "load_settings", lambda: {"parameters": {"customs_net_weight_method": "ratio", "customs_net_weight_ratio": 0.5}})
    assert compute_net_weight(100, 10) == 98.0


def test_tickets_gross_is_box_sum_net_minus_and_price_rule():
    boxes = [7.5] * 13 + [9.5] * 8
    lines = [dict(PET, sku="A", qty=52, unit_price=39.99), dict(PET, sku="B", qty=32, unit_price=49.99)]
    d = build_customs_from_tickets([_ticket(boxes, lines)], PROFILE, order_no="JUS13DD21")
    assert d.total_pieces == 21 and d.total_gross_kg == 173.5 and d.total_net_kg == 169.3
    assert len(d.lines) == 1
    ln = d.lines[0]
    assert (ln.qty, ln.unit, ln.unit_price, ln.amount) == (84, "包", 43.80, 3679.20)
    assert ln.gross_kg == 173.5 and ln.net_kg == 169.3 and ln.box_count == 21
    assert ln.price_source == "invoice"
    assert d.remarks == "订单编号：JUS13DD21。仓库编码：SBD1。FBA编码：FBA1。"
    assert d.blocking == []


def test_tickets_total_gross_without_box_list():
    t = {"shipment_id": "F1", "warehouse": "ORF2", "box_count": 35, "gross_kg": 294, "lines": [dict(PET, sku="A", qty=210, unit_price=39.99)]}
    d = build_customs_from_tickets([t, dict(t, shipment_id="F2", warehouse="PSP3")], PROFILE, order_no="JUS5HB")
    assert d.total_pieces == 70 and d.total_gross_kg == 588 and d.total_net_kg == 574.0
    assert d.remarks == "订单编号：JUS5HB。仓库编码：ORF2，PSP3。FBA编码：F1，F2。"


def test_two_hs_two_lines_each_template():
    lines = [dict(PET, sku="A", qty=10, unit_price=10),
             dict(sku="B", qty=5, unit_price=69.99, chinese_name="车载狗栏", hs_code="7326909000", unit="个", brand="DemoBrand", category="pet")]
    d = build_customs_from_tickets([_ticket([10, 10], lines)], PROFILE, order_no="X")
    assert [l.hs_code for l in d.lines] == ["6307909000", "7326909000"]
    assert d.lines[0].declare_elements == "1|2|宠物用|品牌：DemoBrand牌|型号：无型号"
    assert d.lines[1].declare_elements == "1|2|非工业用宠物车载用|铁制|焊接|品牌：DemoBrand牌|型号：无型号"
    assert d.total_amount == 449.95


def test_box_weight_more_than_two_decimals_blocks():
    d = build_customs_from_tickets([_ticket([7.505, 8], [dict(PET, sku="A", qty=2, unit_price=1)])], PROFILE, order_no="X")
    assert any(b["code"] == "weight_precision" for b in d.blocking)
    assert "7.505" in d.blocking[0]["message"]


@pytest.mark.parametrize("v,expect", [("43.805", "43.81"), ("2.675", "2.68"), ("1.005", "1.01")])
def test_unit_price_half_up_not_bankers(v, expect):
    d = build_customs_from_tickets([_ticket([1], [dict(PET, sku="A", qty=1, unit_price=float(v))])], PROFILE, order_no="X")
    assert Decimal(str(d.lines[0].unit_price)) == Decimal(expect)


def test_fishing_without_template_blocks():
    lines = [dict(sku="F", qty=1, unit_price=5, chinese_name="鱼竿", hs_code="9507100000", unit="支", category="fishing")]
    d = build_customs_from_tickets([_ticket([1], lines)], PROFILE, order_no="X")
    assert any(b["code"] == "customs_config_missing" for b in d.blocking)


def test_missing_price_blocks_ticket_line():
    d = build_customs_from_tickets([_ticket([1], [dict(PET, sku="A", qty=1)])], PROFILE, order_no="X")
    assert any(b["code"] == "price_missing" for b in d.blocking)


def test_mixed_box_not_double_counted_in_line(monkeypatch):
    from fba_tool.customs_package import build_customs_data
    from test_customs_package import _sample_pair

    monkeypatch.setattr(cp, "_catalog_hints", lambda sku: {"中文品名": "宠物垫", "单个货值": 10.0, "申报价来源": "lingxing"})
    d = build_customs_data([_sample_pair()], [], PROFILE, source="shipment", order_no="T1")
    # 箱 1 混装 PAD-001 + PAD-002，合并成一行后仍是 2 箱、毛重 23.5
    assert len(d.lines) == 1 and d.lines[0].box_count == 2 and d.lines[0].gross_kg == 23.5
    assert d.lines[0].net_kg == 23.1
