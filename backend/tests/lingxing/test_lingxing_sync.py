"""领星 MCP 客户端、字段映射与 schema 迁移测试。"""
from __future__ import annotations

import json

import pytest

from fba_tool.lingxing_mcp_client import (
    LingxingMcpClient,
    LingxingMcpError,
    extract_list,
    extract_total,
    parse_sse_json_objects,
    unwrap_lingxing_payload,
)
from fba_tool.lingxing_sync import listing_to_product, replenish_to_row, shop_to_row, stock_to_row
from fba_tool.master_db import (
    get_product_by_sku,
    init_master_db,
    list_lingxing_stock_alerts,
    replace_lingxing_replenish,
    upsert_product,
)


@pytest.fixture()
def isolated_app_data(monkeypatch, tmp_path):
    ad = tmp_path / "app_data"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    init_master_db()
    return ad


def test_schema_adds_lingxing_columns_and_tables(isolated_app_data):
    import sqlite3

    from fba_tool.master_db import master_db_path

    conn = sqlite3.connect(master_db_path())
    cols = {r[1] for r in conn.execute("PRAGMA table_info(product_master)")}
    for name in ("parent_asin", "sid", "listing_status", "fulfillment_channel", "lingxing_synced_at", "data_source"):
        assert name in cols
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for name in (
        "lingxing_shop",
        "lingxing_fba_stock",
        "lingxing_replenish",
        "lingxing_asin_perf",
        "lingxing_sync_run",
        "lingxing_sync_diff",
        "lingxing_sync_preview_sku",
        "lingxing_sync_preview_field",
    ):
        assert name in tables
    conn.close()


def test_listing_mapper_is_identity_only():
    rec = listing_to_product(
        {
            "seller_sku": "MSKU-1",
            "asin": "B0TESTASIN1",
            "fnsku": "X001",
            "item_name": "Dog Toy",
            "brand": "DemoBrand",
            "parent_asin": "B0PARENT",
            "sid": 9001,
            "status": 1,
            "fulfillment_channel_type": "AMAZON_NA",
            "price": 19.99,
            "carton_length": 99,
            "hs_code": "SHOULD-NOT-MAP",
        },
        "2026-09-19T00:00:00+00:00",
    )
    assert rec is not None
    assert rec["sku"] == "MSKU-1"
    assert rec["asin"] == "B0TESTASIN1"
    assert rec["english_name"] == "Dog Toy"
    assert rec["listing_status"] == "active"
    assert "carton_length" not in rec
    assert "hs_code" not in rec
    assert "chinese_name" not in rec
    extra = rec["extra_data"]["lingxing"]
    assert extra["price"] == 19.99


def test_preview_does_not_write_master_until_confirm(isolated_app_data):
    from fba_tool.lingxing_preview import (
        build_listing_preview,
        confirm_lingxing_preview,
    )
    from fba_tool.master_db import create_lingxing_sync_run, finish_lingxing_sync_run

    upsert_product(
        {
            "sku": "MSKU-1",
            "asin": "B0OLD",
            "fnsku": "OLD",
            "english_name": "Keep Me",
            "brand": "LocalBrand",
            "carton_length": 40,
            "hs_code": "123456",
        }
    )
    rec = listing_to_product(
        {
            "seller_sku": "MSKU-1",
            "asin": "B0NEWASINXX",
            "fnsku": "NEWFNSKU",
            "item_name": "Amazon Title Should Not Default Write",
            "brand": "AmazonBrand",
            "sid": 9001,
            "status": 1,
        },
        "2026-09-19T00:00:00+00:00",
    )
    run_id = create_lingxing_sync_run()
    summary = build_listing_preview(run_id, [rec])
    finish_lingxing_sync_run(run_id, "preview_pending", [], summary, None)

    saved = get_product_by_sku("MSKU-1")
    assert saved["asin"] == "B0OLD"
    assert saved["english_name"] == "Keep Me"
    assert saved["carton_length"] == 40
    assert saved["hs_code"] == "123456"
    assert summary["changed"] == 1

    from fba_tool.lingxing_preview import serialize_preview

    payload = serialize_preview(run_id)
    fields = {f["field"]: f for f in payload["groups"]["changed"][0]["fields"]}
    assert fields["asin"]["default_checked"] is True
    assert fields["fnsku"]["default_checked"] is True
    assert fields["english_name"]["default_checked"] is False
    assert fields["brand"]["default_checked"] is False

    confirm_lingxing_preview(run_id, [{"sku": "MSKU-1", "fields": ["asin", "fnsku"]}])
    saved = get_product_by_sku("MSKU-1")
    assert saved["asin"] == "B0NEWASINXX"
    assert saved["fnsku"] == "NEWFNSKU"
    assert saved["english_name"] == "Keep Me"
    assert saved["brand"] == "LocalBrand"
    assert saved["carton_length"] == 40
    assert saved["hs_code"] == "123456"


def test_new_sku_defaults_checked_mismatch_does_not(isolated_app_data):
    from fba_tool.lingxing_preview import build_listing_preview, serialize_preview
    from fba_tool.master_db import create_lingxing_sync_run

    upsert_product({"sku": "LOCAL-A", "asin": "B0SHARE"})
    rec = listing_to_product(
        {
            "seller_sku": "LX-NEW",
            "asin": "B0SHARE",
            "fnsku": "FNEW",
            "item_name": "New Item",
            "sid": 9001,
        },
        "2026-09-19T00:00:00+00:00",
    )
    run_id = create_lingxing_sync_run()
    summary = build_listing_preview(run_id, [rec])
    assert summary["sku_mismatch"] == 1
    payload = serialize_preview(run_id)
    row = payload["groups"]["sku_mismatch"][0]
    assert row["sku"] == "LX-NEW"
    assert all(not f["default_checked"] for f in row["fields"])
    assert get_product_by_sku("LX-NEW") is None


def test_preview_dedupes_same_msku_across_shops(isolated_app_data):
    from fba_tool.lingxing_preview import build_listing_preview, serialize_preview
    from fba_tool.master_db import create_lingxing_sync_run, replace_lingxing_shops

    replace_lingxing_shops(
        [
            {"sid": 9001, "name": "DemoBrand-US", "country": "美国", "country_code": "US"},
            {"sid": 9002, "name": "DemoBrand-CA", "country": "加拿大", "country_code": "CA"},
        ]
    )
    us = listing_to_product(
        {
            "seller_sku": "MSKU-DUP",
            "asin": "B0USASINXXX",
            "fnsku": "XUS001",
            "item_name": "US Title",
            "sid": 9001,
            "status": 1,
        },
        "2026-09-19T00:00:00+00:00",
    )
    ca = listing_to_product(
        {
            "seller_sku": "MSKU-DUP",
            "asin": "B0CAASINYYY",
            "fnsku": "XCA001",
            "item_name": "CA Title",
            "sid": 9002,
            "status": 1,
        },
        "2026-09-19T00:00:00+00:00",
    )
    run_id = create_lingxing_sync_run()
    summary = build_listing_preview(run_id, [ca, us, ca])
    assert summary["new"] == 1
    payload = serialize_preview(run_id)
    rows = payload["groups"]["new"]
    assert len(rows) == 1
    assert rows[0]["sku"] == "MSKU-DUP"
    fields = {f["field"]: f["remote_value"] for f in rows[0]["fields"]}
    assert fields["asin"] == "B0USASINXXX"
    assert fields["sid"] == "9001"


def test_confirm_rejects_stale_run(isolated_app_data):
    from fba_tool.lingxing_preview import LingxingPreviewError, confirm_lingxing_preview
    from fba_tool.master_db import create_lingxing_sync_run, finish_lingxing_sync_run

    old = create_lingxing_sync_run()
    finish_lingxing_sync_run(old, "preview_pending", [], {}, None)
    new = create_lingxing_sync_run()
    finish_lingxing_sync_run(new, "preview_pending", [], {}, None)
    try:
        confirm_lingxing_preview(old, [])
        raise AssertionError("should reject stale run")
    except LingxingPreviewError as exc:
        assert exc.status_code == 409


def test_lingxing_upsert_overwrites_identity_keeps_carton(isolated_app_data):
    upsert_product(
        {
            "sku": "MSKU-1",
            "asin": "B0OLD",
            "fnsku": "OLD",
            "english_name": "Old Name",
            "carton_length": 40,
            "carton_width": 30,
            "carton_height": 20,
            "carton_weight": 2.5,
            "hs_code": "123456",
            "chinese_name": "报关名",
            "qty_per_box": 24,
        }
    )
    rec = listing_to_product(
        {
            "seller_sku": "MSKU-1",
            "asin": "B0NEWASINXX",
            "fnsku": "NEWFNSKU",
            "item_name": "New English",
            "sid": 9001,
            "status": 1,
        },
        "2026-09-19T00:00:00+00:00",
    )
    upsert_product(rec)
    saved = get_product_by_sku("MSKU-1")
    assert saved is not None
    assert saved["asin"] == "B0NEWASINXX"
    assert saved["fnsku"] == "NEWFNSKU"
    assert saved["english_name"] == "New English"
    assert saved["carton_length"] == 40
    assert saved["carton_weight"] == 2.5
    assert saved["hs_code"] == "123456"
    assert saved["chinese_name"] == "报关名"
    assert saved["qty_per_box"] == 24
    assert saved["data_source"] == "mixed"
    assert saved["lingxing_synced_at"]


def test_stock_alerts_from_replenish(isolated_app_data):
    replace_lingxing_replenish(
        [
            {
                "sku": "OUT-1",
                "asin": "B0DEMO0099",
                "sid": 9001,
                "title": "Fence",
                "days_fba": 0,
                "fulfillable": 0,
                "qty_local_to_fba": 120,
                "out_stock_date": "2026-09-01",
                "extra_json": None,
            }
        ],
        "2026-09-19T00:00:00+00:00",
    )
    alerts = list_lingxing_stock_alerts()
    assert len(alerts) == 1
    assert alerts[0]["asin"] == "B0DEMO0099"
    assert "断货" in alerts[0]["message"] or "可售天数" in alerts[0]["message"]


def test_sse_and_lingxing_envelope():
    sse = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"{\\"success\\":true,\\"code\\":1,\\"data\\":{\\"list\\":[{\\"sid\\":1}]}}"}]}}\n\n'
    objects = parse_sse_json_objects(sse)
    assert len(objects) == 1
    payload = unwrap_lingxing_payload(objects[0])
    rows = extract_list(payload)
    assert rows[0]["sid"] == 1

    with pytest.raises(LingxingMcpError):
        unwrap_lingxing_payload({"success": False, "code": 0, "msg": "无权限", "error_details": {"code": 8002}})


def test_extract_nested_listing_total():
    payload = {"data": {"data": {"list": [{"a": 1}, {"a": 2}], "total": 136}}}
    assert extract_total(payload) == 136
    assert len(extract_list(payload)) == 2


def test_qps_throttle_sleeps_between_calls():
    sleeps: list[float] = []

    class FakeResp:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        text = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "x"}},
            }
        )

    class FakeSession:
        def post(self, *args, **kwargs):
            return FakeResp()

    client = LingxingMcpClient(
        "test-key",
        min_interval=1.05,
        session=FakeSession(),
        sleeper=lambda s: sleeps.append(s),
    )
    client.initialize()
    client.initialize()
    assert sleeps, "第二次请求应等待以满足 QPS=1"
    assert sleeps[-1] >= 1.0


def test_shop_to_row_uses_amazon_sid_not_snowflake():
    rec = shop_to_row(
        {
            "store_id": "100000000000000001",
            "s_id": 9001,
            "name": "DemoBrand-US",
            "country_code": "US",
            "platform_name": "Amazon",
            "currency": "USD",
        }
    )
    assert rec is not None
    assert rec["sid"] == 9001
    assert rec["currency"] == "USD"
    assert shop_to_row({"store_id": "100000000000000001", "name": "x"}) is None


def test_iter_pages_advances_by_page_size():
    class FakeResp:
        def __init__(self, payload):
            self.status_code = 200
            self.headers = {"Content-Type": "application/json"}
            self.text = json.dumps({"jsonrpc": "2.0", "id": 1, "result": payload})

    class FakeSession:
        def __init__(self):
            self.bodies = []

        def post(self, *args, **kwargs):
            raw = json.loads(kwargs["data"].decode() if isinstance(kwargs.get("data"), bytes) else kwargs["data"])
            method = raw.get("method")
            if method == "initialize":
                return FakeResp({"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {}})
            if method == "notifications/initialized":
                return FakeResp({})
            args_obj = (raw.get("params") or {}).get("arguments") or {}
            if (raw.get("params") or {}).get("name") == "search":  # S9：action 前先 search 确认 toolType=read
                found = {"success": True, "code": 1, "data": {"toolId": args_obj.get("toolId"), "toolType": "read"}}
                return FakeResp({"content": [{"type": "text", "text": json.dumps(found)}]})
            params = args_obj.get("params") or {}
            self.bodies.append(params)
            offset = int(params.get("offset") or 0)
            if offset == 0:
                rows = [{"sku": f"A{i}"} for i in range(50)]
            elif offset == 50:
                rows = [{"sku": f"B{i}"} for i in range(36)]
            else:
                rows = []
            inner = {"success": True, "code": 1, "data": {"list": rows, "total": 86}}
            return FakeResp({"content": [{"type": "text", "text": json.dumps(inner)}]})

    session = FakeSession()
    client = LingxingMcpClient("k", min_interval=1.0, session=session, sleeper=lambda _s: None)
    pages = list(client.iter_pages("erp_listing", {"pvi_ids": ""}, start_offset=0, page_size=50))
    offsets = [p[0] for p in pages]
    assert offsets[0] == 0
    assert 50 in offsets
    assert sum(len(p[1]) for p in pages) == 86


def test_nested_replenish_mapper():
    rec = replenish_to_row(
        {
            "displayInfo": {
                "itemName": "Fence",
                "asinList": ["B0DEMO0099"],
                "productList": [{"sku": "DEMO-BARRIER"}],
            },
            "suggestInfo": {
                "availableSaleDaysFba": 4,
                "quantitySugLocalToFba": 98,
                "outStockDate": "2026-09-23",
            },
            "salesInfo": {"salesTotal30": 122},
            "amazonQuantityInfo": {"afnFulfillableQuantity": 9},
            "basicInfo": {"relationListing": [{"msku": "DEMO-BARRIER-FBA", "storeId": 9001}]},
        }
    )
    assert rec is not None
    assert rec["sku"] == "DEMO-BARRIER-FBA"
    assert rec["asin"] == "B0DEMO0099"
    assert rec["days_fba"] == 4
    assert rec["qty_local_to_fba"] == 98
    assert rec["sid"] == 9001


def test_stock_mapper():
    row = stock_to_row(
        {
            "msku": "S1",
            "asin": "B0X",
            "fnsku": "F1",
            "sid": 9001,
            "afn_fulfillable_quantity": 12,
            "inv_age_0_to_30_days": 10,
        }
    )
    assert row is not None
    assert row["sku"] == "S1"
    assert row["fulfillable"] == 12
    assert row["age_0_30"] == 10
