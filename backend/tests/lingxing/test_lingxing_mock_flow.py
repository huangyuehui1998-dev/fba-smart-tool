"""T-1：领星同步用进程内 mock，不调用真实 MCP。

流程：preview → 只确认部分字段 → manual 来源的字段不被覆盖 → 第二次 preview 差异为 0。
第二次预览使用确认后的快照（已写入的身份字段 + 被锁定的手填英文名）。
"""
from __future__ import annotations

import pytest

from fba_tool.lingxing_sync import listing_to_product
from fba_tool.master_db import (
    create_lingxing_sync_run,
    finish_lingxing_sync_run,
    get_product_by_sku,
    init_master_db,
    upsert_product,
)
from fba_tool.product_fields import SOURCE_MANUAL, mark_field_sources


@pytest.fixture()
def isolated_app_data(monkeypatch, tmp_path):
    ad = tmp_path / "app_data"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    init_master_db()
    return ad


def _preview(record):
    from fba_tool.lingxing_preview import build_listing_preview

    run_id = create_lingxing_sync_run()
    summary = build_listing_preview(run_id, [record])
    finish_lingxing_sync_run(run_id, "preview_pending", [], summary, None)
    return run_id, summary


def test_partial_confirm_keeps_manual_field_then_second_preview_is_clean(isolated_app_data):
    from fba_tool.lingxing_preview import confirm_lingxing_preview

    upsert_product(
        {
            "sku": "TEST_A",
            "asin": "B0OLDASIN01",
            "fnsku": "X00TEST001",
            "english_name": "Handmade Name",
            "brand": "LocalBrand",
        }
    )
    mark_field_sources("TEST_A", ["english_name"], SOURCE_MANUAL)

    remote = {
        "seller_sku": "TEST_A",
        "asin": "B0NEWASIN01",
        "fnsku": "X00TEST002",
        "item_name": "Remote Title",
        "brand": "LocalBrand",
    }
    run_id, summary = _preview(listing_to_product(remote, "2026-10-20T00:00:00+00:00"))
    assert summary["changed"] == 1

    result = confirm_lingxing_preview(
        run_id,
        [{"sku": "TEST_A", "fields": ["asin", "fnsku", "english_name"]}],
    )
    saved = get_product_by_sku("TEST_A")
    assert saved["asin"] == "B0NEWASIN01"
    assert saved["fnsku"] == "X00TEST002"
    assert saved["english_name"] == "Handmade Name"
    assert saved["brand"] == "LocalBrand"
    assert (saved.get("field_sources") or {}).get("english_name") == SOURCE_MANUAL
    assert result["locked_skipped"] >= 1

    remote["item_name"] = "Handmade Name"
    _run2, summary2 = _preview(listing_to_product(remote, "2026-10-20T01:00:00+00:00"))
    assert summary2["changed"] == 0
    assert summary2["unchanged"] == 1
