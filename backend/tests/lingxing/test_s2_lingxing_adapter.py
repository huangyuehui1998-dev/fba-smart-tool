"""S2-1：领星字段映射（以 MCP erp_listing 真实返回为准）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fba_tool.lingxing_adapter import load_field_map, map_listing_row

FIX = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "lingxing" / "erp_listing_sample.json"


def _rows():
    return json.loads(FIX.read_text(encoding="utf-8"))["list"]


def test_field_map_file_is_valid():
    fm = load_field_map()
    assert fm["listing"]["sku"][0] == "msku"
    assert fm["listing"]["listing_price"][0] == "listing_price"
    assert fm["carton"]["available_in_mcp"] is False


def test_map_real_listing_rows():
    out = [map_listing_row(r) for r in _rows()]
    first = out[0]
    assert first["sku"] == "DEMO-MSKU-001-FBA"
    assert first["fnsku"] == "X00TEST001"
    assert first["asin"] == "B0DEMO0001"
    assert first["listing_price"] == 15.99
    assert first["listing_price_currency"] == "USD"
    # 划线价 list_price 38.97 不能当成售价
    assert all(o["listing_price"] != 38.97 for o in out)


def test_price_fallback_and_invalid():
    assert map_listing_row({"msku": "A", "price": "12.30"})["listing_price"] == 12.3
    assert map_listing_row({"msku": "A", "listing_price": "", "landed_price": "9.9"})["listing_price"] == 9.9
    assert map_listing_row({"msku": "A", "listing_price": "abc"})["listing_price"] is None
    assert map_listing_row({"msku": "A", "listing_price": "0"})["listing_price"] is None
    assert map_listing_row({"fnsku": "X0"}) is None


def test_excel_header_aliases():
    row = {"MSKU": "A-1", "FNSKU": "X00TEST001", "价格": "19.99"}
    m = map_listing_row(row)
    assert m["sku"] == "A-1" and m["listing_price"] == 19.99
