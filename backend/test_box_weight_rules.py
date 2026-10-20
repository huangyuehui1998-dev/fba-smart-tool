"""PR-1a：毛重规则、混装上限、总毛重、单箱装量、Decimal。"""
from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from fba_tool.boxing import box_metrics, dataframe_to_sku_rows, generate_box_plan, plans_to_editor_df
from fba_tool.box_weight import carton_gross_kg, carrier_tare, mixed_box_would_exceed
from fba_tool.data_processing import check_gross_weight_consistency, validate_step1, with_computed_columns
from fba_tool.fba_compliance import to_decimal
from fba_tool.models import SkuRow


def _row(**kw):
    base = {
        "SKU简称": "TEST_A",
        "FNSKU": "X00TEST001",
        "发货总数": 100,
        "单箱装量": 4,
        "箱长(cm)": 40,
        "箱宽(cm)": 22,
        "箱高(cm)": 22,
        "单个重量(kg)": 0,
        "空纸箱重(kg)": 0.3,
        "单箱毛重(kg)": 1.8,
    }
    base.update(kw)
    return base


def test_rule_1a_missing_unit_weight_requires_confirm_without_suggestion():
    warnings = check_gross_weight_consistency(with_computed_columns(pd.DataFrame([_row()])))
    assert len(warnings) == 1
    assert warnings[0]["kind"] == "unit_weight_missing"
    assert warnings[0]["requires_confirm"] is True
    assert warnings[0]["suggested_gross_kg"] is None
    assert "0.3" not in warnings[0]["message"]


def test_rule_1b_missing_gross_is_warning_only():
    row = _row(**{"单个重量(kg)": 2, "单箱毛重(kg)": None, "空纸箱重(kg)": 0.5, "单箱装量": 10})
    warnings = check_gross_weight_consistency(with_computed_columns(pd.DataFrame([row])))
    assert warnings[0]["kind"] == "gross_missing"
    assert warnings[0]["requires_confirm"] is False
    assert warnings[0]["suggested_gross_kg"] == 20.5


def test_rule_2_mismatch_suggests_calculated_value():
    row = _row(**{"单个重量(kg)": 2, "空纸箱重(kg)": 0.5, "单箱装量": 10, "单箱毛重(kg)": 2.05})
    warnings = check_gross_weight_consistency(with_computed_columns(pd.DataFrame([row])))
    assert warnings[0]["kind"] == "gross_mismatch"
    assert warnings[0]["requires_confirm"] is True
    assert warnings[0]["suggested_gross_kg"] == 20.5


def test_full_carton_uses_declared_gross_and_total_is_box_count_times_it():
    df = with_computed_columns(pd.DataFrame([_row(**{"单个重量(kg)": 0, "单箱毛重(kg)": 7.5})]))
    assert float(df.loc[0, "预计总毛重(kg)"]) == pytest.approx(25 * 7.5)


def test_carton_qty_must_be_positive_integer():
    df = pd.DataFrame([_row(**{"单箱装量": 2.5, "单个重量(kg)": 1})])
    errors = validate_step1(df)
    assert any(field == "单箱装量" for _idx, field in errors)
    assert validate_step1(pd.DataFrame([_row(**{"单箱装量": 4, "单个重量(kg)": 1})])) == []


def test_mixed_boxes_stay_within_limit_and_peak_is_22_44():
    rows = []
    for sku, qty, unit in (("TEST_A", 11, 1.0), ("TEST_B", 9, 1.0), ("TEST_C", 5, 0.48)):
        rows.append(
            _row(
                **{
                    "SKU简称": sku,
                    "发货总数": qty,
                    "单箱装量": 50,
                    "箱长(cm)": 50,
                    "箱宽(cm)": 40,
                    "箱高(cm)": 30,
                    "单个重量(kg)": unit,
                    "空纸箱重(kg)": 1.0,
                    "单箱毛重(kg)": None,
                }
            )
        )
    sku_rows = dataframe_to_sku_rows(with_computed_columns(pd.DataFrame(rows)))
    plans, _tail = generate_box_plan(sku_rows, max_weight_kg=22.5)
    metrics = box_metrics(plans_to_editor_df(plans), sku_rows)
    mixed = metrics[metrics["SKU种类"] > 1]
    assert not mixed.empty
    assert float(mixed["毛重(kg)"].max()) == pytest.approx(22.44)
    assert float(mixed["毛重(kg)"].max()) <= 22.5


def test_carrier_tare_is_largest_volume_not_max_tare():
    big = SkuRow("BIG", 1, 1, 50, 40, 30, 1, carton_tare_kg=0.4)
    heavy_tare = SkuRow("SMALL", 1, 1, 10, 10, 10, 1, carton_tare_kg=9)
    sku_map = {s.sku: s for s in (big, heavy_tare)}
    assert carrier_tare(["SMALL", "BIG"], sku_map) == 0.4
    assert carton_gross_kg(4, 1, 0.3, 7.5, 4) == 7.5
    assert carton_gross_kg(2, 1, 0.3, 7.5, 4) == pytest.approx(2.3)
    assert mixed_box_would_exceed(21.44, 0.48, 1.0, 22.5) is True
    assert mixed_box_would_exceed(20.96, 0.48, 1.0, 22.5) is False


def test_to_decimal_uses_str_and_rejects_nan():
    assert to_decimal(0.1) == Decimal("0.1")
    with pytest.raises(ValueError):
        to_decimal(float("nan"))


def test_compute_preview_returns_box_metrics():
    from main import app

    client = TestClient(app)
    res = client.post(
        "/api/compute_preview",
        json={"rows": [_row(**{"单个重量(kg)": 1, "单箱毛重(kg)": 4.3, "发货总数": 4})]},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["box_metrics"]
    assert body["total_gross_kg"] == pytest.approx(4.3)
