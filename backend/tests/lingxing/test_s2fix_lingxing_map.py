"""S2-fix D4：领星 local_name 同步进产品库；币种只给符号 "$" 时存 USD。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fba_tool.lingxing_adapter import map_listing_row, normalize_currency
from fba_tool.lingxing_preview import apply_lingxing_field_patch
from fba_tool.lingxing_sync import listing_to_product
from fba_tool.master_db import get_product_by_sku, init_master_db
from fba_tool.product_import import apply_listing_import

SAMPLE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "lingxing" / "erp_listing_sample.json"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    ad = tmp_path / "app_data"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    init_master_db()


@pytest.mark.parametrize("raw,iso", [("$", "USD"), ("US$", "USD"), ("usd", "USD"), ("USD", "USD"),
                                     ("€", "EUR"), ("£", "GBP"), ("C$", "CAD"), ("", None), (None, None)])
def test_normalize_currency(raw, iso):
    assert normalize_currency(raw) == iso


def test_symbol_only_stored_as_usd():
    out = map_listing_row({"msku": "Z2", "currency_symbol": "$", "listing_price": "15.99"})
    assert out["listing_price_currency"] == "USD"


def test_local_name_mapped_from_sample():
    rows = json.loads(SAMPLE.read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows.get("data") or rows.get("list")
    row = [r for r in rows if r.get("local_name")][0]
    assert map_listing_row(row)["local_name"] == row["local_name"]
    prod = listing_to_product(row, "2026-10-16T00:00:00Z")
    assert prod["local_name"] == row["local_name"]


def test_local_name_written_via_mcp_patch():
    apply_lingxing_field_patch("L1", ["local_name"], {"local_name": "宠物床垫"})
    rec = get_product_by_sku("L1")
    assert rec["local_name"] == "宠物床垫"
    assert rec["field_sources"]["local_name"] == "lingxing"
    assert rec["chinese_name"] in (None, "")  # 报关中文品名不被领星品名覆盖


def test_listing_import_currency_symbol_and_local_name():
    csv = "MSKU,价格,币种,品名\nL2,$19.99,$,狗狗围栏\n".encode("utf-8")
    apply_listing_import(csv, "listing.csv")
    rec = get_product_by_sku("L2")
    assert rec["listing_price_currency"] == "USD"
    assert rec["local_name"] == "狗狗围栏"


@pytest.mark.parametrize("row,basis", [
    ({"msku": "Z", "listing_price": "15.99", "price": "16"}, "listing_price"),
    ({"msku": "Z", "price": "16"}, "price"),
    ({"msku": "Z", "landed_price": "17"}, "landed_price"),
])
def test_price_basis_recorded(row, basis):
    assert map_listing_row(row)["listing_price_basis"] == basis


def test_mcp_patch_overrides_manual_listing_price():
    from fba_tool.master_db import patch_product_field

    patch_product_field("M1", "listing_price", 20.0)
    res = apply_lingxing_field_patch("M1", ["listing_price"], {"listing_price": 15.99, "listing_price_basis": "listing_price"})
    rec = get_product_by_sku("M1")
    assert rec["listing_price"] == 15.99 and "listing_price" in res["written"]
