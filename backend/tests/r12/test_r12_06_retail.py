"""R12-06：领星售价写产品库，产品成本留在 CNY。"""
from __future__ import annotations

import io

from fastapi.testclient import TestClient
from openpyxl import Workbook

from fba_tool.declared_value import persist_retail_import, quote_declared_value
from fba_tool.master_db import get_product_by_sku, init_master_db
from fba_tool.product_fields import NEW_PRODUCT_COST_NOTE, OLD_PRODUCT_COST_NOTE, _migrate_legacy_product_cost
from fba_tool.product_import import apply_listing_import
from test_masterdata_rules import _isolated


def _sku_count():
    from fba_tool.master_db import _connect

    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM product_master").fetchone()[0]


def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_empty_library_upload_does_not_create_skus(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    client = TestClient(__import__("main").create_app())
    payload = _xlsx([
        ["MSKU", "国家", "币种", "价格"],
        ["TEST_NO_MATCH", "美国", "USD", 39.99],
    ])
    res = client.post(
        "/api/master-data/retail-prices/upload",
        files={"file": ("listing.xlsx", payload, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["parsed_count"] == 1
    assert body["imported_count"] == 0
    assert body["unmatched_count"] == 1
    assert _sku_count() == 0
    warned = client.post("/api/master-data/retail-prices", json={
        "source": "lingxing_mcp",
        "products": [{"msku": "IGNORED"}],
        "rows": [{"msku": "TEST_NO_MATCH", "country": "美国", "currency": "USD", "price": 39.99}],
    })
    assert warned.status_code == 200
    assert "products 参数已忽略，按产品库匹配" in warned.json()["warnings"]
    assert _sku_count() == 0


def test_matched_mcp_write_and_old_apply_does_not_create(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from fba_tool.product_fields import set_product_fields

    set_product_fields("TEST_A", {"fnsku": "X00TESTA1"}, "manual")
    result = persist_retail_import(
        [{"msku": "TEST_A", "country": "美国", "currency": "USD", "price": 39.99}],
        source="lingxing_mcp",
    )
    assert result["imported_count"] == 1
    saved = get_product_by_sku("TEST_A")
    assert saved["listing_price"] == 39.99
    assert saved["listing_price_currency"] == "USD"
    assert saved["retail_source"] == "lingxing_mcp"
    assert _sku_count() == 1
    apply_listing_import(_xlsx([
        ["MSKU", "国家", "币种", "价格"],
        ["TEST_NEW", "美国", "USD", 12],
        ["TEST_A", "美国", "USD", 40],
    ]), "listing.xlsx")
    assert get_product_by_sku("TEST_NEW") is None
    assert get_product_by_sku("TEST_A")["listing_price"] == 40
    assert _sku_count() == 1


def test_product_cost_migration_and_quote(monkeypatch, tmp_path):
    ad = _isolated(monkeypatch, tmp_path)
    from fba_tool.master_db import _connect

    with _connect() as conn:
        conn.execute(
            "INSERT INTO product_master (sku, declared_value, extra_data, updated_at) VALUES (?,?,?,?)",
            ("TEST_COST_A", 80, f"note {OLD_PRODUCT_COST_NOTE}", "2026-01-01T00:00:00+00:00"),
        )
        conn.commit()
        _migrate_legacy_product_cost(conn)
        conn.commit()
    saved = get_product_by_sku("TEST_COST_A")
    assert saved["product_cost_cny"] == 80
    assert saved["product_cost_currency"] == "CNY"
    assert saved["declared_value"] in (None, "")
    assert NEW_PRODUCT_COST_NOTE in (saved.get("extra_data") or "")
    with _connect() as conn:
        history = conn.execute(
            "SELECT field FROM product_field_history WHERE sku = ?",
            ("TEST_COST_A",),
        ).fetchone()
    assert history[0] == "product_cost_cny"
    quoted = quote_declared_value(
        [{"sku": "TEST_COST_A", "qty": 1, "product_cost_cny": 80}],
        "retail",
        7.2,
        month="2026-10",
    )
    assert quoted["lines"][0]["price_source"] == "product_cost"
    assert quoted["total_usd"] == 11.11
    init_master_db()
    assert (ad / "fba_master.db").is_file()
