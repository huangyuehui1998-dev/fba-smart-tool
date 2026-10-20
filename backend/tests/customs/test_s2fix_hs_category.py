"""S2-fix 第3项：产品库 category 字段、hs_declare_template 表（按 HS+品类）、钓具 SKU 缺报关配置标记/筛选/导出阻断。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fba_tool import customs_package as cp
from fba_tool.customs_export import CustomsExportBlocked, export_customs_package
from fba_tool.hs_config import customs_config_missing, get_hs_template, list_hs_templates, render_elements, upsert_hs_template
from fba_tool.master_db import get_product_by_sku, init_master_db, list_products, patch_product_field, upsert_product
from test_customs_package import _sample_pair

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "customs" / "报关资料模板.xlsx"
PROFILE = {"id": "t", "name": "测试公司", "credit_code": "X", "signed_at": "武汉", "domestic_source": "武汉"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    ad = tmp_path / "app_data"
    ad.mkdir()
    db = ad / "fba_master.db"
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: db)
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    init_master_db()
    return db


def test_schema_v3_tables_and_category(isolated):
    with sqlite3.connect(isolated) as c:
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        cols = {r[1] for r in c.execute("PRAGMA table_info(product_master)")}
        assert c.execute("PRAGMA user_version").fetchone()[0] >= 3
    assert {"hs_declare_template", "fba_warehouse", "customs_rule_profile", "forwarder_template", "shipment_ticket"} <= names
    assert "category" in cols


def test_pet_templates_seeded_no_fishing_preset():
    t = get_hs_template("pet", "6307909000")
    assert t["elements_pattern"].startswith("1|2|{用途}|")
    t2 = get_hs_template("pet", "7326909000")
    assert "铁制|焊接" in t2["elements_pattern"]
    assert list_hs_templates("fishing") == []  # 钓具 HS 等报关行确认后由用户录入，不预置


def test_render_elements():
    t = get_hs_template("pet", "7326909000")
    out = render_elements(t, {"品牌": "DemoBrand", "型号": "无型号"})
    assert out == "1|2|非工业用宠物车载用|铁制|焊接|品牌：DemoBrand牌|型号：无型号"
    t = get_hs_template("pet", "6307909000")
    assert render_elements(t, {"品牌": "DemoBrand", "型号": "无型号"}) == "1|2|宠物用|品牌：DemoBrand牌|型号：无型号"


def test_fishing_sku_flagged_missing_then_ok_after_config():
    upsert_product({"sku": "FISH-001", "chinese_name": "钓鱼铅坠", "hs_code": "9507900000", "brand": "DemoFishBrand"})
    patch_product_field("FISH-001", "category", "fishing")
    rec = get_product_by_sku("FISH-001")
    assert rec["category"] == "fishing"
    assert "hs_declare_template" in customs_config_missing(rec)
    items = {p["sku"]: p for p in list_products()}
    assert items["FISH-001"]["customs_config_status"] == "缺报关配置"
    upsert_hs_template({"category": "fishing", "hs_code": "9507900000", "customs_name": "钓鱼用具",
                        "elements_pattern": "1|2|{用途}|品牌：{品牌}牌|型号：{型号}", "default_purpose": "钓鱼用",
                        "declare_unit": "个"})
    assert customs_config_missing(get_product_by_sku("FISH-001")) == []
    assert {p["sku"]: p for p in list_products()}["FISH-001"]["customs_config_status"] == ""


def test_api_filter_missing_customs_config():
    from main import app

    upsert_product({"sku": "FISH-002", "chinese_name": "鱼钩", "hs_code": "9507200000"})
    patch_product_field("FISH-002", "category", "fishing")
    upsert_product({"sku": "PET-1", "chinese_name": "宠物垫", "hs_code": "6307909000"})
    patch_product_field("PET-1", "category", "pet")
    r = TestClient(app).get("/api/master-data/list", params={"customs_status": "missing"})
    skus = [i["sku"] for i in r.json()["items"]]
    assert "FISH-002" in skus and "PET-1" not in skus


def test_hs_template_api_roundtrip():
    from main import app

    c = TestClient(app)
    r = c.post("/api/master-data/hs-templates", json={"category": "fishing", "hs_code": "9507200000",
                                                       "customs_name": "鱼钩", "elements_pattern": "1|2|{用途}|品牌：{品牌}牌|型号：{型号}"})
    assert r.status_code == 200
    assert any(t["hs_code"] == "9507200000" for t in c.get("/api/master-data/hs-templates", params={"category": "fishing"}).json()["items"])
    bad = c.post("/api/master-data/hs-templates", json={"category": "fishing", "hs_code": "95A", "elements_pattern": "x"})
    assert bad.status_code == 422


def test_customs_uses_template_and_blocks_fishing_without_config(monkeypatch):
    hints = {"中文品名": "钓鱼铅坠", "海关编码": "9507900000", "品牌": "DemoFishBrand", "品类": "fishing",
             "单个货值": 9.99, "申报价来源": "lingxing"}
    monkeypatch.setattr(cp, "_catalog_hints", lambda sku: dict(hints))
    data = cp.build_customs_data([_sample_pair()], [], PROFILE, source="shipment", order_no="F1")
    assert any(b["code"] == "customs_config_missing" for b in data.blocking)
    assert "宠物" not in data.lines[0].declare_elements
    with pytest.raises(CustomsExportBlocked) as ei:
        export_customs_package(data, TEMPLATE.read_bytes())
    assert "缺报关配置" in str(ei.value)

    upsert_hs_template({"category": "fishing", "hs_code": "9507900000", "customs_name": "钓鱼用具",
                        "elements_pattern": "1|2|{用途}|品牌：{品牌}牌|型号：{型号}", "default_purpose": "钓鱼用"})
    data = cp.build_customs_data([_sample_pair()], [], PROFILE, source="shipment", order_no="F1")
    assert data.blocking == []
    assert data.lines[0].declare_elements == "1|2|钓鱼用|品牌：DemoFishBrand牌|型号：无型号"


def test_pet_line_uses_hs_template(monkeypatch):
    hints = {"中文品名": "车载狗栏", "海关编码": "7326909000", "品牌": "DemoBrand", "品类": "pet",
             "单个货值": 30.0, "申报价来源": "lingxing"}
    monkeypatch.setattr(cp, "_catalog_hints", lambda sku: dict(hints))
    data = cp.build_customs_data([_sample_pair()], [], PROFILE, source="shipment", order_no="P1")
    assert data.lines[0].declare_elements == "1|2|非工业用宠物车载用|铁制|焊接|品牌：DemoBrand牌|型号：无型号"
