"""U5-M2-P2 币种：合成夹具。≠币种已关，≠Publish。

两条写入路径不要混成一句：

- 零售导入 ``import_retail_rows``（G3 / Accept C4）：美国站非 USD 用 fx 换算后写入；
  缺汇率抛 ``FX_RATE_REQUIRED``（接口 409）。非美国站即使有汇率也跳过（「非目标站点」）。
  币种为空跳过，HTTP 200 带明细，不默认 USD。
- 领星 xlsx 预览 ``lingxing_listing_xlsx.parse_listing_xlsx``（G2）：站点币种不符时记异常
  「价格币种应为 USD」或「价格币种应为 CAD」，该行不写入、不换算。
  加拿大站且币种就是 CAD 的行仍留在预览里，但 ``resolve_declared_price`` / 确认不会把它当成美国站申报价。
"""
from __future__ import annotations

import io
import json
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from fba_tool.customs_package import money_half_up
from fba_tool.declared_value import FxRateRequired, import_retail_rows, persist_retail_import
from fba_tool.lingxing_adapter import map_listing_row
from fba_tool.lingxing_listing_xlsx import parse_listing_xlsx
from fba_tool.lingxing_preview import apply_lingxing_field_patch, preview_price_info
from fba_tool.lingxing_sync import listing_to_product
from fba_tool.product_fields import resolve_declared_price
from test_masterdata_rules import _isolated

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "synthetic" / "currency" / "rows.json"
US_CAD_ANOMALY = "US 价格币种应为 USD，文件里是 CAD，该行不写入"
CA_USD_ANOMALY = "CA 价格币种应为 CAD，文件里是 USD，该行不写入"


def _rows():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {row["id"]: row for row in payload["rows"]}


def _xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["MSKU", "国家", "币种", "价格", "店铺"])
    for row in rows:
        ws.append([row["msku"], row["country"], row["currency"], row["price"], row.get("shop") or ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_g3_c4_retail_skips_non_us_and_converts_us_foreign_currency():
    rows = _rows()
    products = {row["msku"]: {"fnsku": "X00TEST"} for row in rows.values()}
    fx = {"CAD/USD": "1.25"}
    mixed = import_retail_rows(
        [rows["us_usd"], rows["ca_cad"], rows["us_empty"], rows["us_cad"]],
        products,
        source="lingxing_mcp",
        fx_by_pair=fx,
    )
    assert mixed["prices"]["TEST_US_PETMAT"] == 39.99
    converted = float(money_half_up(Decimal("65.11") / Decimal("1.25")))
    assert mixed["prices"]["TEST_US_CAD"] == converted
    assert converted != 65.11
    assert "TEST_CA_PETMAT" not in mixed["prices"]
    assert "TEST_US_EMPTY" not in mixed["prices"]
    assert any(item["msku"] == "TEST_CA_PETMAT" and item["reason"] == "非目标站点" for item in mixed["skipped"])
    assert any(item["msku"] == "TEST_US_EMPTY" and item["reason"] == "币种为空" for item in mixed["skipped"])
    canada_only = import_retail_rows([rows["ca_cad"]], products, source="lingxing_mcp", fx_by_pair=fx)
    assert canada_only["prices"] == {}
    assert canada_only["parsed_count"] == 0
    with pytest.raises(FxRateRequired) as exc:
        import_retail_rows([rows["us_cad"]], products, source="lingxing_mcp", fx_by_pair={})
    assert exc.value.code == "FX_RATE_REQUIRED"


def test_g3_c4_retail_api_409_and_empty_currency_200(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from fastapi.testclient import TestClient
    from fba_tool.product_fields import set_product_fields
    from main import create_app

    set_product_fields("TEST_US_CAD", {"fnsku": "X00TESTUSC"}, "manual")
    set_product_fields("TEST_US_EMPTY", {"fnsku": "X00TESTEMP"}, "manual")
    set_product_fields("TEST_CA_PETMAT", {"fnsku": "X00TESTCA1"}, "manual")
    client = TestClient(create_app())
    missing = client.post("/api/master-data/retail-prices", json={
        "source": "lingxing_mcp",
        "rows": [_rows()["us_cad"]],
        "fx_by_pair": {},
    })
    assert missing.status_code == 409
    assert missing.json()["detail"]["code"] == "FX_RATE_REQUIRED"
    skipped = client.post("/api/master-data/retail-prices", json={
        "source": "lingxing_mcp",
        "rows": [_rows()["us_empty"], _rows()["ca_cad"]],
        "fx_by_pair": {"CAD/USD": "1.25"},
    })
    assert skipped.status_code == 200, skipped.text
    body = skipped.json()
    assert body["prices"] == {}
    reasons = {item["reason"] for item in body["skipped"]}
    assert "币种为空" in reasons
    assert "非目标站点" in reasons


def test_g2_xlsx_anomaly_copy_does_not_convert():
    rows = _rows()
    parsed = parse_listing_xlsx(
        _xlsx([rows["us_usd"], rows["us_cad"], rows["ca_usd"], rows["ca_cad"], rows["us_empty"]]),
        "synthetic-currency.xlsx",
    )
    messages = [item["message"] for item in parsed["anomalies"]]
    assert US_CAD_ANOMALY in messages
    assert CA_USD_ANOMALY in messages
    assert any("价格币种应为 USD" in text for text in messages)
    assert any("价格币种应为 CAD" in text for text in messages)
    assert any(item["sku"] == "TEST_US_EMPTY" and item["message"] == "缺少币种，未写入" for item in parsed["anomalies"])
    by_sku = {item["sku"]: item for item in parsed["products"]}
    assert set(by_sku) == {"TEST_US_PETMAT", "TEST_CA_PETMAT"}
    assert by_sku["TEST_US_PETMAT"]["listing_price"] == 39.99
    assert by_sku["TEST_US_PETMAT"]["listing_price_currency"] == "USD"
    assert by_sku["TEST_US_PETMAT"]["listing_price_site"] == "US"
    assert by_sku["TEST_CA_PETMAT"]["listing_price"] == 65.11
    assert by_sku["TEST_CA_PETMAT"]["listing_price_currency"] == "CAD"
    assert by_sku["TEST_CA_PETMAT"]["listing_price_site"] == "CA"
    assert resolve_declared_price(by_sku["TEST_CA_PETMAT"]) == (None, "")
    # xlsx 行的取价字段是 price，来源名是 lingxing_price；金额仍是美元 39.99，不是加元。
    assert resolve_declared_price(by_sku["TEST_US_PETMAT"]) == (39.99, "lingxing_price")


def test_g1_resolve_blocks_ca_and_non_usd_but_keeps_manual_and_us_usd():
    cad = {
        "listing_price": 65.11,
        "listing_price_currency": "CAD",
        "listing_price_site": "CA",
        "listing_price_basis": "price",
    }
    assert resolve_declared_price(cad) == (None, "")
    manual = dict(cad, declared_value=12.5, field_sources={"declared_value": "manual"})
    assert resolve_declared_price(manual) == (12.5, "manual")
    us = {
        "listing_price": 39.99,
        "listing_price_currency": "USD",
        "listing_price_site": "US",
        "listing_price_basis": "listing_price",
        "declared_value": 12.5,
        "field_sources": {"declared_value": "manual"},
    }
    assert resolve_declared_price(us) == (39.99, "lingxing")
    assert resolve_declared_price({"listing_price": 15.99, "listing_price_basis": "listing_price"}) == (15.99, "lingxing")
    site_only = {"listing_price": 65.11, "listing_price_site": "加拿大", "listing_price_basis": "listing_price"}
    assert resolve_declared_price(site_only) == (None, "")


def test_g1_preview_and_confirm_do_not_replace_us_price_with_cad(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from fba_tool.master_db import get_product_by_sku
    from fba_tool.product_fields import set_product_fields

    set_product_fields("TEST_US_PETMAT", {
        "listing_price": 39.99,
        "listing_price_currency": "USD",
        "listing_price_site": "US",
        "listing_price_basis": "listing_price",
        "declared_value": 12.5,
        "fnsku": "X00TESTUS1",
    }, "manual")
    remote = {
        "listing_price": 65.11,
        "listing_price_currency": "CAD",
        "listing_price_site": "CA",
        "listing_price_basis": "price",
        "regular_price": 70,
    }
    info = preview_price_info(remote, get_product_by_sku("TEST_US_PETMAT"))
    assert info["declared_price"] == pytest.approx(39.99)
    assert any("美国站申报价" in text for text in info["warnings"])
    bare = preview_price_info(remote, None)
    assert bare["declared_price"] is None
    res = apply_lingxing_field_patch(
        "TEST_US_PETMAT",
        ["listing_price", "regular_price", "listing_price_site"],
        remote,
    )
    saved = get_product_by_sku("TEST_US_PETMAT")
    assert "listing_price" in res["skipped_invalid"]
    assert saved["listing_price"] == 39.99
    assert saved["listing_price_currency"] == "USD"
    assert saved["listing_price_site"] == "US"
    assert saved["declared_value"] == 12.5
    assert resolve_declared_price(saved)[0] == pytest.approx(39.99)


def test_manual_declared_value_survives_us_retail_sync(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from fba_tool.master_db import get_product_by_sku
    from fba_tool.product_fields import set_product_fields

    set_product_fields("TEST_US_PETMAT", {"fnsku": "X00TESTUS1", "declared_value": 12.5}, "manual")
    result = persist_retail_import([_rows()["us_usd"]], source="lingxing_mcp")
    assert result["imported_count"] == 1
    saved = get_product_by_sku("TEST_US_PETMAT")
    assert saved["declared_value"] == 12.5
    assert saved["listing_price"] == 39.99
    assert saved["listing_price_currency"] == "USD"
    assert resolve_declared_price(saved) == (39.99, "lingxing")


def test_adapter_empty_currency_does_not_feed_declared_price():
    bare = listing_to_product(
        {"msku": "TEST_US_EMPTY", "listing_price": "39.99", "marketplace": "美国"},
        "2026-10-26T00:00:00Z",
    )
    assert bare["listing_price"] is None
    assert not bare.get("listing_price_currency")
    mapped = map_listing_row({"msku": "TEST_US_EMPTY", "listing_price": "39.99"})
    assert mapped["listing_price"] == 39.99
    assert mapped["listing_price_currency"] in ("", None)
    cad = listing_to_product(
        {
            "msku": "TEST_CA_PETMAT",
            "listing_price": "65.11",
            "currency_symbol": "C$",
            "marketplace": "加拿大",
        },
        "2026-10-26T00:00:00Z",
    )
    assert cad["listing_price"] == 65.11
    assert cad["listing_price_currency"] == "CAD"
    assert cad["listing_price_site"] == "加拿大"
    assert resolve_declared_price(cad) == (None, "")


def test_product_import_blank_or_non_usd_currency_does_not_write_price(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from fba_tool.master_db import get_product_by_sku
    from fba_tool.product_import import apply_listing_import, preview_listing_import

    csv = (
        "MSKU,FNSKU,ASIN,价格,币种\n"
        "TEST_US_EMPTY,X00TESTEMP,B0TESTEMP1,39.99,\n"
        "TEST_CA_PETMAT,X00TESTCA1,B0TESTCA01,65.11,CAD\n"
        "TEST_US_PETMAT,X00TESTUS1,B0TESTUS01,39.99,USD\n"
    ).encode("utf-8")
    preview = preview_listing_import(csv, "currency.csv")
    messages = [item["message"] for item in preview["errors"]]
    assert any("币种为空" in text for text in messages)
    assert any("不是 USD" in text and "CAD" in text for text in messages)
    applied = apply_listing_import(csv, "currency.csv")
    assert applied["written"] == 1
    assert get_product_by_sku("TEST_US_EMPTY") is None
    assert get_product_by_sku("TEST_CA_PETMAT") is None
    saved = get_product_by_sku("TEST_US_PETMAT")
    assert saved["listing_price"] == 39.99
    assert saved["listing_price_currency"] == "USD"
    assert resolve_declared_price(saved) == (39.99, "lingxing")
