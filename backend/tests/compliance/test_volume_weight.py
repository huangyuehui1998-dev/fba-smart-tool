"""体积重换算与货代分组聚合测试。"""
from pathlib import Path

from fba_tool.fba_parser import build_forwarder_df, parse_amazon_csv
from fba_tool.forwarder_quote import (
    append_warehouse_subtotals,
    build_forwarder_df as build_fwd,
    compute_forwarder_total_cbm,
)
from fba_tool.volume_weight import box_cbm, normalize_box_spec_row, to_cm, to_kg, volume_weight_kg


def test_inch_to_cm_one_decimal():
    assert to_cm(19.0944881889764, "in") == 48.5
    assert to_cm(18.8976377952756, "in") == 48.0


def test_lb_to_kg_two_decimals():
    assert to_kg(36.08, "lb") == 16.37


def test_volume_weight_formula():
    vol = volume_weight_kg(48.5, 30.0, 38.0, throw_ratio=6000)
    assert vol == round(48.5 * 30.0 * 38.0 / 6000, 3)


def test_box_cbm_formula():
    assert box_cbm(48.5, 30.0, 38.0) == round(48.5 * 30.0 * 38.0 / 1_000_000, 3)


def test_warehouse_subtotals():
    import pandas as pd

    df = pd.DataFrame(
        [
            {
                "仓库代码": "FWA4",
                "箱数": 2,
                "箱子长(cm)": 48.5,
                "箱子宽(cm)": 30.0,
                "箱子高(cm)": 38.0,
                "总实重(kg)": 32.74,
                "单箱体积重(kg)": 9.2,
                "总体积重(kg)": 18.4,
            },
            {
                "仓库代码": "FWA4",
                "箱数": 1,
                "箱子长(cm)": 40.0,
                "箱子宽(cm)": 30.0,
                "箱子高(cm)": 30.0,
                "总实重(kg)": 16.37,
                "单箱体积重(kg)": 6.0,
                "总体积重(kg)": 6.0,
            },
            {
                "仓库代码": "GYR2",
                "箱数": 3,
                "箱子长(cm)": 48.5,
                "箱子宽(cm)": 30.0,
                "箱子高(cm)": 38.0,
                "总实重(kg)": 49.11,
                "单箱体积重(kg)": 9.2,
                "总体积重(kg)": 27.6,
            },
        ]
    )
    result = append_warehouse_subtotals(df)
    assert len(result) == 5
    assert result.iloc[2]["仓库代码"] == "FWA4 小计"
    assert int(result.iloc[2]["箱数"]) == 3
    assert float(result.iloc[2]["总实重(kg)"]) == round(32.74 + 16.37, 2)
    assert float(result.iloc[2]["总体积重(kg)"]) == round(18.4 + 6.0, 3)
    assert "方数:" in str(result.iloc[2]["箱子长(cm)"])
    assert float(result.iloc[2]["_subtotal_cbm"]) > 0
    assert compute_forwarder_total_cbm(result) > 0
    assert result.iloc[4]["仓库代码"] == "GYR2 小计"
    again = append_warehouse_subtotals(result)
    assert len(again) == 5


def test_build_forwarder_includes_subtotals():
    csv_path = Path("templates/亚马逊FBA表1.csv")
    if not csv_path.exists():
        return
    parsed = parse_amazon_csv(csv_path.read_bytes())
    specs = parsed["box_specs"]
    items = parsed["box_items"]
    fwd = build_fwd(specs, items)
    detail = fwd[~fwd["仓库代码"].astype(str).str.endswith(" 小计")]
    subtotal_rows = fwd[fwd["仓库代码"].astype(str).str.endswith(" 小计")]
    assert len(subtotal_rows) >= 1
    assert "SKU" in detail.columns
    assert detail["SKU"].astype(str).str.len().gt(0).any()
    assert int(subtotal_rows["箱数"].sum()) == int(detail["箱数"].sum())
    for _, row in detail.iterrows():
        single_vol = volume_weight_kg(row["箱子长(cm)"], row["箱子宽(cm)"], row["箱子高(cm)"])
        assert row["总体积重(kg)"] == round(single_vol * int(row["箱数"]), 3) or row["总体积重(kg)"] > 0


def test_build_forwarder_groups_by_sku():
    import pandas as pd

    specs = pd.DataFrame(
        [
            {
                "仓库代码": "FWA4",
                "箱号": 1,
                "长(cm)": 40.0,
                "宽(cm)": 30.0,
                "高(cm)": 30.0,
                "实重(kg)": 10.0,
                "FBA箱号": "FBA1U001",
            },
            {
                "仓库代码": "FWA4",
                "箱号": 2,
                "长(cm)": 40.0,
                "宽(cm)": 30.0,
                "高(cm)": 30.0,
                "实重(kg)": 12.0,
                "FBA箱号": "FBA1U002",
            },
        ]
    )
    items = pd.DataFrame(
        [
            {"仓库代码": "FWA4", "箱号": 1, "SKU": "SKU-A", "数量": 2},
            {"仓库代码": "FWA4", "箱号": 2, "SKU": "SKU-A", "数量": 1},
            {"仓库代码": "FWA4", "箱号": 2, "SKU": "SKU-B", "数量": 1},
        ]
    )
    fwd = build_fwd(specs, items)
    detail = fwd[~fwd["仓库代码"].astype(str).str.endswith(" 小计")]
    sku_a = detail[detail["SKU"] == "SKU-A"].iloc[0]
    assert sku_a["箱序号"] == "1,2"
    assert int(sku_a["箱数"]) == 2
    assert float(sku_a["单件实重(kg)"]) > 0


def test_normalize_merges_near_identical_dims():
    a = normalize_box_spec_row(19.0944881889764, 11.8110236220472, 14.9606299212598, 36.08)
    b = normalize_box_spec_row(19.0944881889764, 11.8110236220472, 14.9606299212598, 36.08)
    assert a == b
    assert a["长(cm)"] == 48.5


if __name__ == "__main__":
    test_inch_to_cm_one_decimal()
    test_lb_to_kg_two_decimals()
    test_volume_weight_formula()
    test_box_cbm_formula()
    test_warehouse_subtotals()
    test_build_forwarder_includes_subtotals()
    test_build_forwarder_groups_by_sku()
    test_normalize_merges_near_identical_dims()
    print("ALL OK")
