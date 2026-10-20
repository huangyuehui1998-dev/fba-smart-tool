"""FBA 排箱物理红线单元测试。"""
from fba_tool.boxing import box_metrics, dataframe_to_sku_rows, generate_box_plan, plans_to_editor_df
from fba_tool.excel_export import build_box_matrix
from fba_tool.fba_compliance import (
    FBA_MAX_SIDE_CM,
    FBA_MAX_STANDARD_GROSS_KG,
    check_box_count_limit,
    evaluate_fba_boxing_compliance,
)
import pandas as pd


def _sku_row(sku: str, qty: int, per_box: int, l: float, w: float, h: float, unit_kg: float, tare: float = 0.5):
    return {
        "SKU简称": sku,
        "FNSKU": "",
        "发货总数": qty,
        "单箱装量": per_box,
        "箱长(cm)": l,
        "箱宽(cm)": w,
        "箱高(cm)": h,
        "单个重量(kg)": unit_kg,
        "空纸箱重(kg)": tare,
        "单箱毛重(kg)": None,
    }


def test_carton_side_warning():
    df = pd.DataFrame([_sku_row("BIG", 10, 10, 100, 40, 30, 1.0)])
    sku_rows = dataframe_to_sku_rows(df)
    comp = evaluate_fba_boxing_compliance(pd.DataFrame(), sku_rows, pd.DataFrame())
    assert comp["side_warning_count"] == 1
    assert comp["carton_side_warnings"][0]["sku"] == "BIG"
    assert comp["blocked"] is False


def test_gross_weight_blocks_standard_box():
    # 每箱 10 件 × 2.5 kg + 0.5 tare = 25.5 kg > 22.68
    df = pd.DataFrame([_sku_row("HEAVY", 20, 10, 40, 30, 20, 2.5, 0.5)])
    sku_rows = dataframe_to_sku_rows(df)
    plans, _ = generate_box_plan(sku_rows, max_weight_kg=50)
    editor = plans_to_editor_df(plans)
    metrics = box_metrics(editor, sku_rows)
    comp = evaluate_fba_boxing_compliance(editor, sku_rows, metrics)
    assert comp["gross_violation_count"] >= 1
    assert comp["blocked"] is True


def test_single_oversize_exempt_from_gross_block():
    # 单件超大箱：1 件，外箱 70cm 边，毛重可超 50lbs
    gross = 25.0
    df = pd.DataFrame(
        [
            {
                **_sku_row("OS-1", 1, 1, 70, 50, 40, 20.0, 0.5),
                "单箱毛重(kg)": gross,
            }
        ]
    )
    sku_rows = dataframe_to_sku_rows(df)
    plans, _ = generate_box_plan(sku_rows)
    editor = plans_to_editor_df(plans)
    metrics = box_metrics(editor, sku_rows)
    comp = evaluate_fba_boxing_compliance(editor, sku_rows, metrics)
    assert comp["gross_violation_count"] == 0
    assert comp["blocked"] is False


def test_limits_constants():
    assert FBA_MAX_STANDARD_GROSS_KG == round(50 * 0.45359237, 2)
    assert FBA_MAX_SIDE_CM == 63.5


def _editor_with_boxes(count: int) -> pd.DataFrame:
    return pd.DataFrame(
        [{"箱号": i, "来源": "整箱", "SKU简称": "SKU-A", "数量": 1} for i in range(1, count + 1)]
    )


def test_box_count_within_limit_is_silent():
    assert check_box_count_limit(_editor_with_boxes(10)) is None
    assert check_box_count_limit(pd.DataFrame()) is None


def test_box_count_over_partnered_limit_warns_without_blocking():
    editor = _editor_with_boxes(201)
    warning = check_box_count_limit(editor)
    assert warning is not None
    assert warning["box_count"] == 201
    assert warning["limit"] == 200
    assert warning["level"] == "info"
    assert "需拆分" not in warning["message"]

    comp = evaluate_fba_boxing_compliance(editor, [], pd.DataFrame())
    assert comp["box_count_warning"] == warning
    assert warning["message"] in comp["summary_lines"]
    assert comp["blocked"] is False


def test_box_matrix_does_not_drop_boxes_over_amazon_limit():
    """曾用 min(actual, 130) 静默截断，导致第 131 箱起的箱内明细从内部表/STA 消失。"""
    over_limit = 210
    matrix = build_box_matrix(_editor_with_boxes(over_limit))
    box_cols = [c for c in matrix.columns if c != "SKU简称"]
    assert len(box_cols) == over_limit


if __name__ == "__main__":
    test_carton_side_warning()
    test_gross_weight_blocks_standard_box()
    test_single_oversize_exempt_from_gross_block()
    test_limits_constants()
    test_box_count_within_limit_is_silent()
    test_box_count_over_partnered_limit_warns_without_blocking()
    test_box_matrix_does_not_drop_boxes_over_amazon_limit()
    print("ALL OK")
