"""R12-16：疑似把单件重填进单箱毛重。比较用 Decimal，容差 0.01kg。"""
from __future__ import annotations

from decimal import Decimal

import pandas as pd

from fba_tool.data_processing import (
    SUSPECT_THRESHOLD_NOTE,
    SUSPECT_UNIT_TOLERANCE_KG,
    check_gross_weight_consistency,
    gross_is_suspect_unit,
)
from fba_tool.weight_gate import raise_if_weight_unconfirmed
from fastapi import HTTPException
import pytest


def _frame(gross):
    return pd.DataFrame([{
        "SKU简称": "TEST_A",
        "FNSKU": "X00TEST001",
        "发货总数": 8,
        "单箱装量": 4,
        "箱长(cm)": 40,
        "箱宽(cm)": 22,
        "箱高(cm)": 22,
        "单个重量(kg)": 0,
        "空纸箱重(kg)": 0.3,
        "单箱毛重(kg)": gross,
    }])


def test_tolerance_constant_and_boundaries():
    assert SUSPECT_UNIT_TOLERANCE_KG == Decimal("0.01")
    suspect = Decimal("0.5")
    tare = Decimal("0.3")
    assert gross_is_suspect_unit(Decimal("2.3"), 4, tare, suspect) is True
    assert gross_is_suspect_unit(Decimal("2.31"), 4, tare, suspect) is True
    assert gross_is_suspect_unit(Decimal("2.32"), 4, tare, suspect) is False
    fuzzy = 2.3000000000000003
    assert gross_is_suspect_unit(fuzzy, 4, tare, suspect) is True


@pytest.mark.parametrize("gross,hit", [
    (Decimal("2.3"), True),
    (Decimal("2.31"), True),
    (Decimal("2.32"), False),
    (2.3000000000000003, True),
])
def test_check_marks_suspect_unit_in_gross(gross, hit):
    warnings = check_gross_weight_consistency(_frame(gross), suspect_kg=Decimal("0.5"))
    assert warnings[0]["kind"] == "unit_weight_missing"
    assert warnings[0]["requires_confirm"] is True
    assert warnings[0]["suggested_gross_kg"] is None
    assert "0.3" not in warnings[0]["message"]
    if hit:
        assert [item["kind"] for item in warnings] == ["unit_weight_missing", "suspect_unit_in_gross"]
        assert "疑似把单件重填进了单箱毛重" in warnings[1]["message"]
        assert warnings[1]["threshold_note"] == SUSPECT_THRESHOLD_NOTE
        assert warnings[1]["requires_confirm"] is True
        assert warnings[1]["suggested_gross_kg"] is None
    else:
        assert [item["kind"] for item in warnings] == ["unit_weight_missing"]


def test_gross_1_8_emits_missing_and_suspect():
    warnings = check_gross_weight_consistency(_frame(Decimal("1.8")), suspect_kg=Decimal("0.5"))
    assert [item["kind"] for item in warnings] == ["unit_weight_missing", "suspect_unit_in_gross"]
    assert warnings[0]["suggested_gross_kg"] is None
    assert "0.3" not in warnings[0]["message"]
    assert warnings[1]["requires_confirm"] is True


def test_unconfirmed_suspect_blocks_export():
    row = _frame(Decimal("2.3")).to_dict(orient="records")[0]
    with pytest.raises(HTTPException) as ei:
        raise_if_weight_unconfirmed([row], False)
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == "WEIGHT_CONFIRM_REQUIRED"
