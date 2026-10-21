# -*- coding: utf-8 -*-
"""S9-step2 A：手动同步预览展示 regular_price 和“申报会用的正常价及来源”。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fba_tool.lingxing_preview import PRICE_SOURCE_LABELS, preview_price_info


def _recent(days: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def test_new_sku_regular_equal_to_price_declares_listing_price():
    info = preview_price_info({"listing_price": 15.99, "regular_price": 15.99}, None)
    assert info["listing_price"] == 15.99
    assert info["regular_price"] == 15.99
    assert info["regular_price_informative"] is False
    assert info["declared_price"] == 15.99
    assert info["declared_source"] == "lingxing"
    assert info["declared_source_label"] == "售价"


def test_informative_regular_promo_declares_regular():
    info = preview_price_info({"listing_price": 12.0, "regular_price": 16.0}, None)
    assert info["regular_price_informative"] is True
    assert info["declared_price"] == 16.0
    assert info["declared_source_label"] == "正常价 · 领星常规价"


def test_recent_nonpromo_history_used_when_regular_uninformative():
    existing = {"sku": "DEMO-1", "listing_price": 16.0, "last_nonpromo_price": 16.0, "last_nonpromo_at": _recent()}
    info = preview_price_info({"listing_price": 12.0, "regular_price": 12.0}, existing)
    assert info["declared_price"] == 16.0
    assert info["declared_source"] == "lingxing_recent_nonpromo"
    assert info["declared_source_label"] == "正常价 · 近 90 天非促销价"


def test_small_drop_under_threshold_keeps_listing_price():
    existing = {"sku": "DEMO-1", "last_nonpromo_price": 16.0, "last_nonpromo_at": _recent()}
    info = preview_price_info({"listing_price": 15.5}, existing)
    assert info["declared_price"] == 15.5 and info["declared_source"] == "lingxing"
    assert info["regular_price"] is None


def test_expired_history_not_used():
    existing = {"sku": "DEMO-1", "last_nonpromo_price": 16.0, "last_nonpromo_at": _recent(120)}
    info = preview_price_info({"listing_price": 12.0}, existing)
    assert info["declared_price"] == 12.0 and info["declared_source_label"] == "售价"


def test_list_price_never_used_as_normal_price():
    info = preview_price_info({"listing_price": 15.99, "regular_price": 15.99, "list_price": 38.97}, None)
    assert info["declared_price"] == 15.99 and info["declared_source"] == "lingxing"


def test_no_remote_price_falls_back_to_local_master():
    existing = {"sku": "DEMO-1", "listing_price": 9.5, "listing_price_basis": "listing_price"}
    info = preview_price_info({}, existing)
    assert info["listing_price"] == 9.5 and info["declared_price"] == 9.5


def test_labels_cover_all_d12_sources():
    for src in ("lingxing", "lingxing_regular", "lingxing_recent_nonpromo"):
        assert PRICE_SOURCE_LABELS[src]


def test_serialize_preview_includes_price_info(tmp_path, monkeypatch):
    from fba_tool import lingxing_preview as lp

    run_id = 4242
    lp.build_listing_preview(run_id, [{"sku": "DEMO-PRICE-1-FBA", "asin": "B0DEMO0101", "fnsku": "X00TEST101",
                                       "listing_price": 12.0, "regular_price": 16.0,
                                       "listing_price_basis": "listing_price"}])
    payload = lp.serialize_preview(run_id)
    rows = [r for g in payload["groups"].values() for r in g if r["sku"] == "DEMO-PRICE-1-FBA"]
    assert rows, payload
    info = rows[0]["price_info"]
    assert info["regular_price"] == 16.0
    assert info["declared_price"] == 16.0 and info["declared_source_label"] == "正常价 · 领星常规价"
