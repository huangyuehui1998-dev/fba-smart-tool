"""R12-04：缺价 409，逐行回退，数字汇率不再 500。"""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from fba_tool.declared_value import MissingPrice, quote_declared_value


def test_missing_price_is_409_and_never_zero():
    client = TestClient(__import__("main").app)
    cost = client.post("/api/declared-value/quote", json={
        "basis": "cost", "month": "2026-10", "fx": 7.2,
        "lines": [{"sku": "TEST_A", "qty": 1}],
    })
    assert cost.status_code == 409
    assert cost.json()["detail"]["code"] == "DECLARED_VALUE_MISSING"
    assert "TEST_A" in cost.json()["detail"]["message"]

    fob = client.post("/api/declared-value/quote", json={
        "basis": "fob", "month": "2026-10", "fx": 7.2,
        "lines": [{"sku": "TEST_A", "qty": 1}],
    })
    assert fob.status_code == 409
    assert fob.json()["detail"]["missing"][0]["tried"] == ["manual_fob", "legacy", "purchase"]

    retail = client.post("/api/declared-value/quote", json={
        "basis": "retail", "month": "2026-10", "fx": 7.2,
        "lines": [{"sku": "TEST_B", "qty": 2}],
    })
    assert retail.status_code == 409
    assert retail.json()["detail"]["code"] == "DECLARED_VALUE_MISSING"
    assert retail.json().get("total_usd") is None


def test_numeric_fx_is_200_and_bad_fx_is_422():
    client = TestClient(__import__("main").app)
    ok = client.post("/api/declared-value/quote", json={
        "basis": "cost", "month": "2026-10", "fx": 7.2,
        "lines": [{"sku": "TEST_A", "qty": 1, "purchase_cny": 50}],
    })
    assert ok.status_code == 200
    assert ok.json()["total_usd"] == 6.94
    bad = client.post("/api/declared-value/quote", json={
        "basis": "cost", "month": "2026-10", "fx": "abc",
        "lines": [{"sku": "TEST_A", "qty": 1, "purchase_cny": 50}],
    })
    assert bad.status_code == 422


def test_fob_per_line_legacy_and_purchase():
    mixed = quote_declared_value(
        [
            {"sku": "TEST_A", "qty": 80, "fob_value": 30, "fob_currency": "USD"},
            {"sku": "TEST_B", "qty": 48, "legacy_usd": "49.99"},
        ],
        "fob",
        7.2,
        month="2026-10",
    )
    assert mixed["total_usd"] == 4799.52
    assert mixed["lines"][0]["price_source"] == "manual_fob"
    assert mixed["lines"][0]["notice"] == ""
    assert mixed["lines"][1]["price_source"] == "legacy"
    assert "历史申报价" in mixed["lines"][1]["notice"]
    assert "历史申报价" in mixed["fob_source_notice"]

    purchase = quote_declared_value(
        [{"sku": "TEST_A", "qty": 1, "purchase_price_cny": 50}],
        "fob",
        7.2,
        month="2026-10",
        fob_domestic_cost_rate=0,
    )
    assert purchase["total_usd"] == 6.94
    assert purchase["lines"][0]["price_source"] == "purchase"
    assert purchase["fob_source_notice"] == ""


def test_none_is_not_zero_on_the_money_path():
    with pytest.raises(MissingPrice):
        quote_declared_value(
            [{"sku": "TEST_A", "qty": 2, "purchase_cny": None}],
            "cost",
            Decimal("7.2"),
            month="2026-10",
        )
