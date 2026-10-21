"""S2-2：产品库新增字段（listing_price / declare_unit / field_source_json）、字段归属锁定、申报价来源。"""
from __future__ import annotations

import sqlite3

import pytest

from fba_tool import master_db
from fba_tool.lingxing_adapter import get_listing_price
from fba_tool.master_db import get_product_by_sku, init_master_db, invoice_hints_from_master, patch_product_field, upsert_product
from fba_tool.product_fields import get_field_sources, resolve_declared_price, set_product_fields


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    ad = tmp_path / "app_data"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    init_master_db()
    return ad


def test_migration_adds_columns_to_old_db(tmp_path, monkeypatch):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE product_master (sku TEXT PRIMARY KEY, asin TEXT, fnsku TEXT, declared_value REAL, updated_at TEXT NOT NULL)")
    conn.execute("INSERT INTO product_master VALUES ('OLD-1','B0','X0', 12.5, '2026-01-01')")
    conn.commit(); conn.close()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: db)
    init_master_db()
    init_master_db()  # 重复执行安全
    rec = get_product_by_sku("OLD-1")
    assert rec["declared_value"] == 12.5          # 老数据不丢
    assert rec["listing_price"] is None and rec["declare_unit"] is None
    with sqlite3.connect(db) as c:
        assert c.execute("PRAGMA user_version").fetchone()[0] >= 2


def test_lingxing_price_written_with_source():
    set_product_fields("A", {"listing_price": 15.99, "listing_price_currency": "USD"}, "lingxing")
    rec = get_product_by_sku("A")
    assert rec["listing_price"] == 15.99 and rec["listing_price_at"]
    assert get_field_sources("A")["listing_price"] == "lingxing"
    assert get_listing_price("A") == 15.99
    assert get_listing_price("NOPE") is None


def test_manual_fields_locked_against_lingxing():
    patch_product_field("A", "declare_unit", "个")
    assert get_field_sources("A")["declare_unit"] == "manual"
    res = set_product_fields("A", {"declare_unit": "件"}, "lingxing")
    assert res["skipped_locked"] == ["declare_unit"]
    assert get_product_by_sku("A")["declare_unit"] == "个"


def test_declared_price_resolution():
    """用户 2026-10-16 定：领星 listing_price > 手填 > 领星 price/landed_price > 旧 declared_value。"""
    upsert_product({"sku": "A", "declared_value": 29.99})            # 历史值（来源未知）
    assert resolve_declared_price(get_product_by_sku("A")) == (29.99, "legacy")
    patch_product_field("A", "declared_value", 18.0)                 # 手填：领星没值时用
    assert resolve_declared_price(get_product_by_sku("A")) == (18.0, "manual")
    set_product_fields("A", {"listing_price": 15.99, "listing_price_basis": "listing_price"}, "lingxing")
    assert resolve_declared_price(get_product_by_sku("A")) == (15.99, "lingxing")  # 领星有值，手填不覆盖
    assert resolve_declared_price({}) == (None, "")


def test_price_fallback_fields_rank_below_manual():
    set_product_fields("B", {"listing_price": 14.0, "listing_price_basis": "landed_price"}, "lingxing")
    assert resolve_declared_price(get_product_by_sku("B")) == (14.0, "lingxing_landed_price")
    patch_product_field("B", "declared_value", 18.0)
    assert resolve_declared_price(get_product_by_sku("B")) == (18.0, "manual")
    upsert_product({"sku": "C", "declared_value": 9.0})
    set_product_fields("C", {"listing_price": 12.0, "listing_price_basis": "price"}, "lingxing")
    assert resolve_declared_price(get_product_by_sku("C")) == (12.0, "lingxing_price")  # 仍高于旧值


def test_manual_listing_price_not_locked_against_lingxing():
    patch_product_field("A", "listing_price", 20.0)
    res = set_product_fields("A", {"listing_price": 15.99}, "lingxing")
    assert res["skipped_locked"] == []
    assert get_product_by_sku("A")["listing_price"] == 15.99
    assert get_field_sources("A")["listing_price"] == "lingxing"


def test_hints_use_listing_price_and_declare_unit():
    set_product_fields("A", {"listing_price": 15.99}, "lingxing")
    patch_product_field("A", "declare_unit", "个")
    h = invoice_hints_from_master(get_product_by_sku("A"))
    assert h["单个货值"] == 15.99 and h["申报价来源"] == "lingxing"
    assert h["declare_unit"] == "个"


def test_invalid_declare_unit_rejected():
    with pytest.raises(ValueError):
        set_product_fields("A", {"declare_unit": ""}, "manual")
    with pytest.raises(ValueError):
        set_product_fields("A", {"listing_price": -1}, "lingxing")


def test_listing_preview_includes_price_and_apply_writes_it():
    from fba_tool.lingxing_preview import CONFIRM_FIELDS, apply_lingxing_field_patch
    from fba_tool.lingxing_sync import listing_to_product

    assert "listing_price" in CONFIRM_FIELDS
    rec = listing_to_product({"msku": "A", "fnsku": "X00DEMO001", "listing_price": "15.99", "list_price": "38.97"}, "t")
    assert rec["listing_price"] == 15.99
    apply_lingxing_field_patch("A", ["listing_price", "fnsku"], rec)
    got = get_product_by_sku("A")
    assert got["listing_price"] == 15.99 and got["fnsku"] == "X00DEMO001"
