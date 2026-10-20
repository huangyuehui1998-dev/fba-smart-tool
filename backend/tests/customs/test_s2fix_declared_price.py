"""S2-fix D2：申报价回落到历史值或无价格时警告；无价格阻断导出、不静默填 0；来源显示在预览数据里。"""
from __future__ import annotations

from pathlib import Path

import pytest

from fba_tool import customs_package as cp
from fba_tool.customs_export import CustomsExportBlocked, export_customs_package
from fba_tool.customs_package import CustomsLineItem, CustomsPackageData, build_customs_data
from test_customs_package import _sample_pair

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "customs" / "报关资料模板.xlsx"
PROFILE = {"id": "t", "name": "测试公司", "credit_code": "X", "signed_at": "武汉", "domestic_source": "武汉"}


def _build(monkeypatch, hints):
    monkeypatch.setattr(cp, "_catalog_hints", lambda sku: dict(hints))
    return build_customs_data([_sample_pair()], [], PROFILE, source="shipment", order_no="T1")


def _codes(data):
    return {w["code"] for w in data.warnings}


def test_lingxing_price_no_warning_but_source_shown(monkeypatch):
    data = _build(monkeypatch, {"中文品名": "宠物垫", "单个货值": 15.99, "申报价来源": "lingxing"})
    assert data.lines[0].unit_price == 15.99
    assert data.lines[0].price_source == "lingxing"
    assert "price_missing" not in _codes(data) and "price_legacy" not in _codes(data)
    assert data.price_sources and data.price_sources[0]["source"] == "lingxing"
    assert data.blocking == []


def test_legacy_price_warns(monkeypatch):
    data = _build(monkeypatch, {"中文品名": "宠物垫", "单个货值": 9.99, "申报价来源": "legacy"})
    assert "price_legacy" in _codes(data)
    w = [w for w in data.warnings if w["code"] == "price_legacy"][0]
    assert "旧数据" in w["message"] and w["skus"]
    assert data.blocking == []


def test_missing_price_blocks_and_not_zero(monkeypatch):
    data = _build(monkeypatch, {"中文品名": "宠物垫"})
    assert "price_missing" in _codes(data)
    assert data.blocking and "申报价" in data.blocking[0]["message"]
    assert data.lines[0].price_source == "none"
    with pytest.raises(CustomsExportBlocked) as ei:
        export_customs_package(data, TEMPLATE.read_bytes())
    assert "申报价" in str(ei.value)


def test_export_blocks_line_with_zero_price_from_edited_payload():
    data = CustomsPackageData(lines=[CustomsLineItem(seq=1, chinese_name="宠物垫", qty=5, unit_price=0, amount=0)])
    with pytest.raises(CustomsExportBlocked):
        export_customs_package(data.to_dict(), TEMPLATE.read_bytes())


def test_big_drop_vs_legacy_warns(monkeypatch):
    data = _build(monkeypatch, {"中文品名": "宠物垫", "单个货值": 15.99, "申报价来源": "lingxing", "历史申报价": 29.99})
    assert "price_drop" in _codes(data)


def test_api_export_returns_422_when_blocked(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app

    data = CustomsPackageData(lines=[CustomsLineItem(seq=1, chinese_name="宠物垫", qty=5, unit_price=0, amount=0)])
    r = TestClient(app).post("/api/customs/export", json={"source": "shipment", "order_no": "T", "data": data.to_dict()})
    assert r.status_code == 422
    assert "申报价" in r.json()["detail"]


# ---------- s2-fix2：手填价没被采用时一律提示 ----------
@pytest.mark.parametrize("manual,lx", [(12.0, 15.99), (16.5, 15.99), (29.99, 15.99)])
def test_manual_price_not_used_always_noted(monkeypatch, manual, lx):
    data = _build(monkeypatch, {"中文品名": "宠物垫", "单个货值": lx, "申报价来源": "lingxing", "手填申报价": manual})
    w = [w for w in data.warnings if w["code"] == "manual_price_not_used"]
    assert w and f"{manual:.2f}" in w[0]["message"] and f"{lx:.2f}" in w[0]["message"]
    assert "未采用" in w[0]["message"]
    assert data.blocking == []


def test_manual_price_used_no_note(monkeypatch):
    data = _build(monkeypatch, {"中文品名": "宠物垫", "单个货值": 18.0, "申报价来源": "manual"})
    assert "manual_price_not_used" not in _codes(data)


def test_hints_carry_unused_manual_price(tmp_path, monkeypatch):
    from fba_tool.master_db import get_product_by_sku, init_master_db, invoice_hints_from_master, patch_product_field
    from fba_tool.product_fields import set_product_fields

    ad = tmp_path / "ad"; ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "m.db")
    init_master_db()
    patch_product_field("A", "declared_value", 16.5)
    set_product_fields("A", {"listing_price": 15.99, "listing_price_basis": "listing_price"}, "lingxing")
    h = invoice_hints_from_master(get_product_by_sku("A"))
    assert h["申报价来源"] == "lingxing" and h["手填申报价"] == 16.5


# ---------- s2-final：相等不提示；降幅按原值比较 ----------
@pytest.mark.parametrize("manual,lx", [(29.99, 29.99), (29.99, 29.990000001), ("29.99", 29.99)])
def test_equal_manual_price_not_noted(monkeypatch, manual, lx):
    data = _build(monkeypatch, {"中文品名": "宠物垫", "单个货值": lx, "申报价来源": "lingxing", "手填申报价": manual})
    assert "manual_price_not_used" not in _codes(data)


def test_unequal_by_one_cent_still_noted(monkeypatch):
    data = _build(monkeypatch, {"中文品名": "宠物垫", "单个货值": 29.98, "申报价来源": "lingxing", "手填申报价": 29.99})
    assert "manual_price_not_used" in _codes(data)


@pytest.mark.parametrize("old,new,hit", [
    (29.99, 23.992, False),   # 正好 20%：原值不触发（先四舍五入成 23.99 会误触发）
    (29.99, 23.9919, True),   # 略超 20%
    (100, 80, False),
    (100, 79.999, True),
    (29.99, 23.995, False),   # 四舍五入会成 24.00，原值仍未超过
])
def test_price_drop_uses_raw_values(monkeypatch, old, new, hit):
    data = _build(monkeypatch, {"中文品名": "宠物垫", "单个货值": new, "申报价来源": "lingxing", "历史申报价": old})
    assert ("price_drop" in _codes(data)) is hit
