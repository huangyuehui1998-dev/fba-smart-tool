"""S1e：FBA 重量/尺寸临界规则（方案 v8 §3.4、§5 第 7 条）。"""
import pandas as pd
import pytest

from fba_tool.fba_compliance import (
    classify_box_weight,
    evaluate_fba_boxing_compliance,
    in_to_cm_exact,
    lb_to_kg_exact,
    side_exceeds,
)
from fba_tool.models import SkuRow
from fba_tool.placement_fee import PlacementFeeEngine


@pytest.mark.parametrize(
    "kg,level",
    [(22.50, "ok"), (22.51, "warn"), (22.68, "warn"), (22.69, "block")],
)
def test_multi_item_weight_thresholds(kg, level):
    assert classify_box_weight(kg) == level


def test_lb_input_uses_exact_factor():
    assert classify_box_weight(lb_to_kg_exact("50.00")) == "warn"
    assert classify_box_weight(lb_to_kg_exact("50.01")) == "block"


def test_side_thresholds_cm_and_inch():
    assert not side_exceeds(63.5)
    assert side_exceeds(63.51)
    assert not side_exceeds(in_to_cm_exact("25.00"))
    assert side_exceeds(in_to_cm_exact("25.01"))


@pytest.mark.parametrize(
    "kg,level",
    [(23, "team_lift"), (45.35, "team_lift"), (45.36, "team_lift"), (45.37, "mechanical_lift")],
)
def test_single_oversize_lift_levels(kg, level):
    assert classify_box_weight(kg, single_oversize=True) == level


def _run(skus, boxes, gross):
    editor = pd.DataFrame(
        [{"箱号": b, "来源": "整箱", "SKU简称": s, "数量": q} for b, s, q in boxes]
    )
    metrics = pd.DataFrame([{"箱号": b, "毛重(kg)": g} for b, g in gross.items()])
    return evaluate_fba_boxing_compliance(editor, skus, metrics)


def test_single_item_oversize_carton_23kg_team_lift():
    sku = SkuRow("OS", 1, 1, 70, 40, 30, 22.5, 0.5)
    comp = _run([sku], [(1, "OS", 1)], {1: 23.0})
    assert comp["blocked"] is False
    assert comp["lift_notices"][0]["label"] == "Team Lift"


def test_single_item_standard_size_23kg_counts_as_oversize():
    """v8：箱内只有 1 件且箱重 > 22.68kg，直接算大件，不阻断，提示 Team Lift。"""
    sku = SkuRow("STD", 1, 1, 40, 30, 20, 22.5, 0.5)
    comp = _run([sku], [(1, "STD", 1)], {1: 23.0})
    assert comp["blocked"] is False
    assert comp["lift_notices"][0]["label"] == "Team Lift"


def test_single_item_mechanical_lift():
    sku = SkuRow("STD", 1, 1, 40, 30, 20, 45.0, 0.37)
    comp = _run([sku], [(1, "STD", 1)], {1: 45.37})
    assert comp["lift_notices"][0]["label"] == "Mechanical Lift"


def test_multi_item_standard_23kg_blocks():
    sku = SkuRow("STD", 4, 2, 40, 30, 20, 11.25, 0.5)
    comp = _run([sku], [(1, "STD", 2)], {1: 23.0})
    assert comp["blocked"] is True
    assert comp["gross_violation_count"] == 1


def test_multi_item_warning_not_blocked():
    sku = SkuRow("STD", 2, 2, 40, 30, 20, 11.0, 0.6)
    comp = _run([sku], [(1, "STD", 2)], {1: 22.6})
    assert comp["blocked"] is False
    assert len(comp["box_weight_warnings"]) == 1


def test_multi_item_long_side_blocks():
    sku = SkuRow("LONG", 4, 2, 92, 60, 40, 2.0, 0.5)
    comp = _run([sku], [(1, "LONG", 2)], {1: 4.5})
    assert comp["blocked"] is True
    assert comp["side_violation_count"] == 1


def test_multi_item_side_exactly_limit_ok():
    sku = SkuRow("EDGE", 4, 2, 63.5, 30, 20, 2.0, 0.5)
    comp = _run([sku], [(1, "EDGE", 2)], {1: 4.5})
    assert comp["blocked"] is False


def test_single_item_long_side_not_blocked():
    sku = SkuRow("LONG1", 1, 1, 70, 30, 20, 5.0, 0.5)
    comp = _run([sku], [(1, "LONG1", 1)], {1: 5.5})
    assert comp["blocked"] is False


def test_unit_heavier_than_limit_is_oversize():
    from fba_tool.fba_compliance import _sku_is_oversize

    assert _sku_is_oversize(SkuRow("H", 1, 1, 40, 30, 20, 22.69, 0.5))
    assert not _sku_is_oversize(SkuRow("L", 1, 1, 40, 30, 20, 22.68, 0.5))


def test_placement_fee_exact_factors():
    e = PlacementFeeEngine()
    assert e.cm_to_in(2.54) == pytest.approx(1.0, abs=1e-12)
    assert e.kg_to_lb(0.45359237) == pytest.approx(1.0, abs=1e-12)
    # 63.5cm 正好 25in，按近似系数会变成 25.0000135
    assert e.cm_to_in(63.5) == pytest.approx(25.0, abs=1e-9)
