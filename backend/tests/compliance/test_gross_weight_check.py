"""Step 1 单箱毛重软校验：录入值 vs 装量×单件重+空箱重。"""
import pandas as pd

from fba_tool.data_processing import check_gross_weight_consistency, with_computed_columns


def _row(sku="SKU-A", per_box=10, unit_kg=2.0, tare=0.5, gross=None):
    return {
        "SKU简称": sku,
        "FNSKU": "",
        "发货总数": 100,
        "单箱装量": per_box,
        "箱长(cm)": 40,
        "箱宽(cm)": 30,
        "箱高(cm)": 30,
        "单个重量(kg)": unit_kg,
        "空纸箱重(kg)": tare,
        "单箱毛重(kg)": gross,
    }


def _check(*rows):
    return check_gross_weight_consistency(with_computed_columns(pd.DataFrame(list(rows))))


def test_matching_gross_weight_is_silent():
    # 10 × 2.0 + 0.5 = 20.5
    assert _check(_row(gross=20.5)) == []


def test_missing_gross_weight_warns_without_confirm():
    """单重有值、毛重空着：只警告，不要求确认。"""
    for gross in (None, 0):
        warnings = _check(_row(gross=gross))
        assert len(warnings) == 1
        assert warnings[0]["kind"] == "gross_missing"
        assert warnings[0]["requires_confirm"] is False
        assert warnings[0]["suggested_gross_kg"] == 20.5


def test_small_deviation_still_requires_confirm():
    # 不一致就要确认，不再按 8% 静默。20.5 与 20.5 仍安静。
    warnings = _check(_row(gross=21.5))
    assert len(warnings) == 1
    assert warnings[0]["kind"] == "gross_mismatch"
    assert warnings[0]["requires_confirm"] is True
    assert warnings[0]["suggested_gross_kg"] == 20.5
    assert _check(_row(gross=20.5)) == []


def test_typo_low_gross_weight_is_flagged():
    """少报毛重不会被任何硬校验拦住，却直接引发重量差异费。"""
    warnings = _check(_row(gross=2.05))
    assert len(warnings) == 1
    w = warnings[0]
    assert w["sku"] == "SKU-A"
    assert w["expected_kg"] == 20.5
    assert w["declared_kg"] == 2.05
    assert w["diff_kg"] < 0
    assert w["deviation_pct"] == 90.0
    assert "请确认" in w["message"]


def test_typo_high_gross_weight_is_flagged():
    warnings = _check(_row(gross=205.0))
    assert len(warnings) == 1
    assert warnings[0]["diff_kg"] > 0


def test_blank_sku_and_zero_theoretical_are_skipped():
    assert _check({**_row(sku=""), "单箱毛重(kg)": 999}) == []
    # 单重为 0 且录了毛重：按 1a 要求确认，不再因为理论值为 0 而静默
    missing = _check(_row(per_box=0, unit_kg=0, tare=0, gross=15))
    assert missing and missing[0]["kind"] == "unit_weight_missing"


def test_only_offending_rows_reported():
    warnings = _check(
        _row(sku="OK", gross=20.5),
        _row(sku="BAD", gross=5.0),
    )
    assert [w["sku"] for w in warnings] == ["BAD"]


if __name__ == "__main__":
    test_matching_gross_weight_is_silent()
    test_missing_gross_weight_warns_without_confirm()
    test_small_deviation_still_requires_confirm()
    test_typo_low_gross_weight_is_flagged()
    test_typo_high_gross_weight_is_flagged()
    test_blank_sku_and_zero_theoretical_are_skipped()
    test_only_offending_rows_reported()
    print("ALL OK")
