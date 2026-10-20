"""S2-fix D1：MCP 预览确认写入时，手填（manual）字段锁定，不被覆盖；写入字段来源记为 lingxing。"""
from __future__ import annotations

import pytest

from fba_tool.lingxing_preview import apply_lingxing_field_patch, build_listing_preview, serialize_preview
from fba_tool.master_db import get_product_by_sku, init_master_db, patch_product_field, upsert_product
from fba_tool.product_fields import get_field_sources


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    ad = tmp_path / "app_data"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    init_master_db()
    upsert_product({"sku": "S1", "fnsku": "X00OLD0001", "asin": "B000000001", "brand": "OLD"})
    return ad


def test_manual_fnsku_not_overwritten_and_source_kept():
    patch_product_field("S1", "fnsku", "X00MANUAL1")
    res = apply_lingxing_field_patch(
        "S1", ["fnsku", "asin", "listing_price"],
        {"fnsku": "X00MCPFNSK", "asin": "B0NEWASIN1", "listing_price": 15.99, "listing_price_currency": "USD"},
    )
    rec = get_product_by_sku("S1")
    src = get_field_sources("S1")
    assert rec["fnsku"] == "X00MANUAL1"
    assert src["fnsku"] == "manual"
    assert "fnsku" in res["skipped_locked"]
    # 未锁定字段照常写入，来源记 lingxing
    assert rec["asin"] == "B0NEWASIN1" and src["asin"] == "lingxing"
    assert rec["listing_price"] == 15.99 and src["listing_price"] == "lingxing"
    assert set(res["written"]) == {"asin", "listing_price"}


def test_non_price_fields_get_lingxing_source():
    apply_lingxing_field_patch("S1", ["brand"], {"brand": "DemoFishBrand"})
    assert get_product_by_sku("S1")["brand"] == "DemoFishBrand"
    assert get_field_sources("S1")["brand"] == "lingxing"


def test_preview_marks_manual_field_locked_and_unchecked():
    patch_product_field("S1", "fnsku", "X00MANUAL1")
    build_listing_preview(1, [{"sku": "S1", "fnsku": "X00MCPFNSK", "asin": "B000000001"}])
    data = serialize_preview(1)
    fields = [f for g in data["groups"].values() for item in g for f in item["fields"]]
    fn = [f for f in fields if f["field"] == "fnsku"][0]
    assert fn["locked"] is True
    assert fn["default_checked"] is False
