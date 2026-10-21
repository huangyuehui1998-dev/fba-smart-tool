"""R12-05：计征汇率按报关完成申报之日取当月，不回退。"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from fba_tool.customs_package import build_customs_data
from fba_tool.declared_value import FxRateRequired, quote_declared_value
from fba_tool.fx_rates import CUSTOMS_MONTHLY_SOURCE, customs_month, snapshot_for_declaration, upsert_rate
from fba_tool.warehouse_db import update_rule_profile
from test_customs_package import _sample_pair
from test_masterdata_rules import _isolated

PROFILE = {"id": "t", "name": "测试公司", "credit_code": "X", "signed_at": "武汉", "domestic_source": "武汉"}


def test_customs_month_is_the_declaration_day():
    assert customs_month("2026-10-31") == "2026-10"
    assert customs_month("2026-11-01") == "2026-11"
    with pytest.raises(ValueError):
        customs_month("2026/11/01")


def test_month_lookup_and_no_fallback(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    upsert_rate({"currency_pair": "USD/CNY", "rate_type": "customs_monthly", "applicable_month": "2026-10", "rate": 7.2})
    upsert_rate({"currency_pair": "USD/CNY", "rate_type": "customs_monthly", "applicable_month": "2026-11", "rate": 7.1})
    october = snapshot_for_declaration("2026-10-31")
    november = snapshot_for_declaration("2026-11-01")
    assert october["fx_rate"] == 7.2
    assert october["fx_applicable_month"] == "2026-10"
    assert october["fx_source"] == CUSTOMS_MONTHLY_SOURCE
    assert november["fx_rate"] == 7.1
    client = TestClient(__import__("main").create_app())
    listed = client.get("/api/fx-rates").json()["items"]
    nov = next(item for item in listed if item["applicable_month"] == "2026-11")
    assert client.delete(f"/api/fx-rates/{nov['id']}").status_code == 200
    assert snapshot_for_declaration("2026-11-01") is None
    assert snapshot_for_declaration("2026-10-31")["fx_rate"] == 7.2


def test_snapshot_reused_after_rate_changes(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    upsert_rate({"applicable_month": "2026-10", "rate": 7.2, "rate_type": "customs_monthly"})
    saved = snapshot_for_declaration("2026-10-31")
    upsert_rate({"applicable_month": "2026-10", "rate": 7.1, "rate_type": "customs_monthly"})
    again = snapshot_for_declaration("2026-10-31", fx_snapshot=saved)
    assert again["fx_rate"] == 7.2
    quoted = quote_declared_value(
        [{"sku": "TEST_COST_A", "qty": 1, "purchase_cny": 80}],
        "cost",
        again,
        month="2026-10",
    )
    assert quoted["total_usd"] == 11.11
    assert quoted["fx_rate"] == 7.2


def test_api_lists_source_sentence_and_rejects_bad_tax_basis(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    client = TestClient(__import__("main").create_app())
    body = client.get("/api/fx-rates").json()
    assert CUSTOMS_MONTHLY_SOURCE in body["customs_monthly_source"]
    assert "销售额发生当日" in body["tax_fx_choices"]
    csv_file = io.BytesIO("currency_pair,rate_type,applicable_month,rate\nUSD/CNY,customs_monthly,2026-10,7.2\n".encode())
    imported = client.post("/api/fx-rates/import", files={"file": ("fx.csv", csv_file, "text/csv")})
    assert imported.status_code == 200
    assert imported.json()["imported"] == 1
    saved = update_rule_profile({"tax_fx_basis": "销售额发生当日"})
    assert saved["tax_fx_basis"] == "day"
    with pytest.raises(ValueError, match="只能是销售额发生当日或当月 1 日"):
        update_rule_profile({"tax_fx_basis": "上周三"})


def test_cost_basis_preview_requires_declaration_month(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    upsert_rate({"applicable_month": "2026-10", "rate": 7.2, "rate_type": "customs_monthly"})
    monkeypatch.setattr(
        "fba_tool.warehouse_db.get_default_rule_profile",
        lambda: {"declared_value_basis": "cost"},
    )
    import fba_tool.customs_package as cp

    monkeypatch.setattr(cp, "_catalog_hints", lambda sku: {"中文品名": "宠物垫", "purchase_cny": 50})
    with pytest.raises(FxRateRequired) as ei:
        build_customs_data(
            [_sample_pair()], [], PROFILE, source="shipment", declaration_date="2026-11-01",
        )
    assert "2026-11" in ei.value.message
    assert "2026-10" not in ei.value.message
    data = build_customs_data(
        [_sample_pair()], [], PROFILE, source="shipment", declaration_date="2026-10-31",
    )
    assert data.fx_rate == 7.2
    assert data.fx_applicable_month == "2026-10"
