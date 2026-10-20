"""PR-2d：主数据缺口、发票字段、申报价口径、净重、STA 配置费。只用合成数据。"""
from __future__ import annotations

import io
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from fba_tool.customs_package import compute_net_weight, money_half_up
from fba_tool.declared_value import (
    FOB_NOTICE,
    convert_fob,
    import_retail_rows,
    parse_listing_table,
    parse_listing_xlsx,
    product_cost_usd,
    quote_declared_value,
    record_sta_placement_fee,
    resolve_retail,
    sta_fee_comparison,
)
from fba_tool.invoice_rules import check_products, invoice_fields
from fba_tool.warehouse_db import get_default_rule_profile, update_rule_profile


def _isolated(monkeypatch, tmp_path):
    ad = tmp_path / "ad"
    ad.mkdir()
    monkeypatch.setenv("FBA_APP_DATA_DIR", str(ad))
    monkeypatch.setenv("FBA_DISABLE_SCHEDULER", "1")
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    from fba_tool.master_db import init_master_db

    init_master_db()
    return ad


def test_master_gaps_two_skus_when_library_empty(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from main import create_app

    client = TestClient(create_app())
    rows = []
    for sku in ("TEST_A", "TEST_B"):
        rows.append({
            "SKU简称": sku,
            "FNSKU": "X00TESTA1" if sku == "TEST_A" else "X00TESTB1",
            "发货总数": 2,
            "单箱装量": 2,
            "箱长(cm)": 30,
            "箱宽(cm)": 20,
            "箱高(cm)": 15,
            "单个重量(kg)": 0.4,
            "空纸箱重(kg)": 0.2,
        })
    res = client.post("/api/compute_preview", json={"rows": rows})
    assert res.status_code == 200, res.text
    gaps = res.json()["master_gaps"]
    assert len(gaps) == 2
    assert {item["sku"] for item in gaps} == {"TEST_A", "TEST_B"}
    for item in gaps:
        assert "asin" in item["missing"] and "unit_dims" in item["missing"]


def test_patch_invoice_unit_clears_missing_unit(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from fba_tool.master_db import patch_product_field, upsert_product

    upsert_product({"sku": "TEST_A", "fnsku": "X00TESTA1", "declare_unit": "个"})
    patched = patch_product_field("TEST_A", "invoice_unit", "套")
    assert patched["invoice_unit"] == "套"
    fields = invoice_fields(patched)
    blocking = check_products({"X00TESTA1": patched}, ["X00TESTA1"], required={"invoice_unit": "单位"})
    assert blocking == []
    assert fields["invoice_unit"] == "套"
    bare = {"sku": "TEST_B", "fnsku": "X00TESTB1", "declare_unit": "个", "invoice": {}}
    assert invoice_fields(bare)["invoice_unit"] == "个"


def test_cost_retail_and_fob_rounding():
    lines = [
        {"sku": "TEST_A", "qty": 80, "retail_usd": "39.99", "purchase_cny": "50", "fob_value": "30", "fob_currency": "USD", "legacy_usd": "39.99"},
        {"sku": "TEST_B", "qty": 48, "retail_usd": "49.99", "purchase_cny": "70", "fob_value": "40", "fob_currency": "USD", "legacy_usd": "49.99"},
    ]
    fx = {
        "fx_rate": "7.2",
        "fx_rate_type": "customs_monthly",
        "fx_applicable_month": "2026-10",
        "fx_source_url": "https://example.test/fx",
        "fx_publish_date": "2026-10-01",
    }
    retail = quote_declared_value(lines, "retail", fx, month="2026-10")
    assert retail["total_usd"] == 5598.72
    assert retail["currency"] == "USD"
    cost = quote_declared_value(lines, "cost", fx, month="2026-10")
    assert cost["total_cny"] == 7360.00
    assert cost["total_usd"] == float(money_half_up(Decimal("7360.00") / Decimal("7.2"))) == 1022.22
    assert cost["avg_usd"] == 7.99
    assert [line["amount_usd"] for line in cost["lines"]] == [555.56, 466.66]
    assert "申报价低于采购价" not in cost["warnings"]
    assert "申报价低于售价 30%" in cost["warnings"]
    assert "申报价高于售价" not in cost["warnings"]
    assert "1021.76" not in repr(cost)
    fob = quote_declared_value(lines, "fob", fx, month="2026-10")
    assert fob["total_usd"] == 4320.00
    fallback = quote_declared_value(
        [{**line, "fob_value": None} for line in lines], "fob", fx, month="2026-10",
    )
    assert fallback["total_usd"] == 5598.72
    assert FOB_NOTICE in fallback["fob_source_notice"]
    later = dict(fx, fx_rate="7.0", fx_applicable_month="2026-11")
    changed = quote_declared_value(lines, "cost", later, month="2026-11")
    assert cost["total_usd"] == 1022.22 and cost["fx_rate"] == 7.2
    assert changed["fx_applicable_month"] == "2026-11"
    assert {cost["fx_rate_type"], cost["fx_source_url"], cost["fx_publish_date"]} == {
        "customs_monthly", "https://example.test/fx", "2026-10-01",
    }


def test_fx_missing_is_409(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from main import create_app

    client = TestClient(create_app())
    res = client.post("/api/declared-value/quote", json={
        "basis": "cost",
        "month": "2026-10",
        "lines": [{"sku": "TEST_A", "qty": 2, "purchase_cny": 50}],
        "fx": {"fx_rate": 0},
    })
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "FX_RATE_REQUIRED"
    assert "2026-10" in res.json()["detail"]["message"]


def test_fob_currency_direction():
    assert convert_fob("216.00", "CNY", "USD", "7.2") == Decimal("30.00")
    assert convert_fob("30.00", "USD", "USD", "7.2") == Decimal("30.00")
    assert convert_fob("30.00", "USD", "CNY", "7.2") == Decimal("216.00")
    with pytest.raises(ValueError, match="暂不支持该币种"):
        convert_fob("30", "EUR", "USD", "7.2")


def test_trade_term_defaults_cf_and_is_independent(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    prof = get_default_rule_profile()
    assert prof["trade_term"] == "C&F"
    assert prof["declared_value_basis"] == "retail"
    updated = update_rule_profile({"trade_term": "FOB"})
    assert updated["trade_term"] == "FOB"
    assert updated["declared_value_basis"] == "retail"
    from fba_tool.customs_package import build_customs_from_tickets

    data = build_customs_from_tickets(
        [{"shipment_id": "FBATEST01", "warehouse": "SBD1", "boxes": [1], "lines": [
            {"sku": "TEST_A", "qty": 1, "unit_price": 1, "chinese_name": "测试", "hs_code": "6307909000"},
        ]}],
        {"name": "测试公司", "credit_code": "X", "signed_at": "武汉", "domestic_source": "武汉"},
        order_no="T1",
    )
    assert data.trade_term == "FOB"
    assert data.declared_value_basis == "retail"


def test_listing_price_layers_and_site_filter():
    products = {"TEST_A": {"fnsku": "X00TESTA1", "declared_value": 35}}
    rows = [
        {"msku": "TEST_A", "country": "美国", "currency": "USD", "price": 39.99, "landed_price": 39.99, "shipping": 0},
        {"msku": "TEST_A", "country": "加拿大", "currency": "CAD", "price": 65.11, "landed_price": 75.66, "shipping": 10.55, "marketplace": "CA"},
    ]
    result = import_retail_rows(rows, products, source="lingxing_mcp", fx_by_pair={"CAD/USD": "1.35"})
    assert result["prices"] == {"TEST_A": 39.99}
    assert result["retail_source"] == "lingxing_mcp"
    assert result["retail_synced_at"]
    assert any(item["reason"] == "非目标站点" for item in result["skipped"])
    failed = resolve_retail(products, xlsx_rows=rows[:1], mcp_error="timeout", fx_by_pair={})
    assert "领星同步失败，已用手动导入值" in failed["notice"]
    assert failed["prices"]["TEST_A"] == 39.99


def test_listing_column_priority_and_empty_currency():
    headers = ["MSKU", "SKU", "国家", "币种", "价格", "售价(总价)", "运费", "优惠价", "List Price", "FNSKU"]
    table = [
        ["TEST_A", "OTHER", "美国", "USD", 29.99, 28.30, 0, 28.30, 40, "X00TESTA1"],
        ["TEST_COMBO", "OTHER", "美国", "USD", 0, 62.68, 0, 0, 0, ""],
        ["TEST_SHIP", "OTHER", "美国", "USD", 0, 75.66, 10.55, 0, 0, ""],
        ["TEST_ZERO", "OTHER", "美国", "USD", 0, 0, 0, 9.99, 19.99, ""],
        ["TEST_EMPTY", "OTHER", "美国", "", 10, 10, 0, 0, 0, ""],
        ["TEST_CA", "OTHER", "加拿大", "CAD", 65.11, 75.66, 10.55, 0, 0, ""],
    ]
    rows = parse_listing_table(headers, table)
    products = {"TEST_A": {"fnsku": "X00TESTA1"}, "TEST_SHIP": {"fnsku": "X00TESTB1"}}
    result = import_retail_rows(rows, products, source="manual_xlsx", fx_by_pair={"CAD/USD": "1.35"})
    by_msku = {item["msku"]: item["price_usd"] for item in result["parsed"]}
    assert by_msku["TEST_A"] == 29.99
    assert by_msku["TEST_COMBO"] == 62.68
    assert by_msku["TEST_SHIP"] == 65.11
    assert "TEST_ZERO" not in by_msku
    assert "TEST_CA" not in by_msku
    assert any(item["reason"] == "币种为空" for item in result["skipped"])
    assert any(item["reason"] == "价格链无值" for item in result["skipped"])
    assert result["imported_count"] == 2
    assert any(item["msku"] == "TEST_COMBO" and item["reason"] == "MSKU 未匹配产品库" for item in result["unmatched"])
    assert any("FNSKU 不一致" in msg for msg in result["warnings"]) is False
    mismatch = import_retail_rows(
        [{"msku": "TEST_A", "country": "美国", "currency": "USD", "price": 10, "fnsku": "X00OTHER"}],
        {"TEST_A": {"fnsku": "X00TESTA1"}},
        source="manual_xlsx",
    )
    assert mismatch["warnings"]
    with pytest.raises(ValueError, match="MSKU"):
        parse_listing_table(["SKU", "价格", "币种"], [["TEST_A", 1, "USD"]])


def test_us_row_with_foreign_currency_uses_fx_or_409():
    row = [{"msku": "TEST_A", "country": "美国", "currency": "CAD", "price": "65.11"}]
    products = {"TEST_A": {"fnsku": "X00TESTA1"}}
    result = import_retail_rows(row, products, source="lingxing_mcp", fx_by_pair={"CAD/USD": "1.25"})
    assert result["prices"]["TEST_A"] == float(money_half_up(Decimal("65.11") / Decimal("1.25")))
    from fba_tool.declared_value import FxRateRequired

    with pytest.raises(FxRateRequired):
        import_retail_rows(row, products, source="lingxing_mcp", fx_by_pair={})
    canada = import_retail_rows(
        [{"msku": "TEST_CA", "country": "加拿大", "currency": "CAD", "price": "65.11"}],
        {},
        source="lingxing_mcp",
        fx_by_pair={"CAD/USD": "1.25"},
    )
    assert canada["prices"] == {}
    assert canada["parsed_count"] == 0


def test_product_cost_fallback_divides_cny():
    assert product_cost_usd(80, "7.2") == Decimal("11.11")
    assert "产品成本→declared_value（CNY）"  # 列映射说明由解析器写入 column_note


def test_product_cost_column_note():
    wb = Workbook()
    ws = wb.active
    ws.append(["SKU", "产品成本"])
    ws.append(["TEST_COST_A", 80])
    buf = io.BytesIO()
    wb.save(buf)
    from fba_tool.product_master_parser import parse_business_product_master

    _records, col_map = parse_business_product_master(buf.getvalue(), "product-info.xlsx")
    assert col_map["column_note"] == "产品成本→declared_value（CNY）"
    assert col_map["declared_value_currency"] == "CNY"


def test_net_weight_tare_changes_cl2_style_total(monkeypatch):
    # 旧 ratio 0.95 × 264 = 250.8。默认 tare_from_carton 用每箱皮重后是 254.4。这是预期变更。
    monkeypatch.setattr(
        "fba_tool.customs_package._net_weight_params",
        lambda: ("tare_from_carton", Decimal("0.2"), Decimal("0.95")),
    )
    assert compute_net_weight(264, 32, [0.3] * 32) == 254.4
    assert float(money_half_up(Decimal("264") * Decimal("0.95"))) == 250.8
    assert compute_net_weight(115.2, 12) == 112.8
    assert compute_net_weight(122.4, 12) == 120.0


def test_sta_fee_out_of_range_persists(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    compared = sta_fee_comparison(63, 180, 200)
    assert compared["out_of_range"] is True
    saved = record_sta_placement_fee("FBATEST01", 200, 63, 180)
    assert saved["out_of_range"] is True
    from fba_tool.ticket_import import get_ticket

    assert get_ticket("FBATEST01")["sta_placement_fee"] == 200


def test_listing_xlsx_round_trip_and_forbidden_names():
    wb = Workbook()
    ws = wb.active
    ws.append(["MSKU", "国家", "币种", "价格", "售价(总价)", "运费"])
    ws.append(["TEST_A", "美国", "USD", 39.99, 39.99, 0])
    buf = io.BytesIO()
    wb.save(buf)
    rows = parse_listing_xlsx(buf.getvalue())
    assert rows[0]["msku"] == "TEST_A"
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "packaging" / "release_manifest.py"
    spec = importlib.util.spec_from_file_location("release_manifest_forbidden", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.forbidden_real_hits(path.parents[1]) == []


def test_tax_fx_basis_locked_for_twelve_months(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    first = update_rule_profile({"tax_fx_basis": "day"})
    assert first["tax_fx_basis"] == "day"
    assert first["tax_fx_locked_until"]
    with pytest.raises(ValueError, match="12 个月内不得变更"):
        update_rule_profile({"tax_fx_basis": "month_first"})
    released = update_rule_profile({"tax_fx_basis": "month_first", "confirm": True})
    assert released["tax_fx_basis"] == "month_first"
