"""入库配置费引擎单元测试 — 2026 政策。"""
from fba_tool.placement_fee import (
    PlacementFeeEngine,
    SPLIT_DISABLED_REASON_STANDARD,
    classify_placement_scenario,
    compute_locked_placement_fee,
    compute_shipment_placement_fees,
    compute_unit_placement_fees,
)

_engine = PlacementFeeEngine()
kg_to_lb = _engine.kg_to_lb


def test_large_standard_no_split_option():
    unit = compute_unit_placement_fees(40, 30, 20, 0.5)
    assert unit["size_class"] == "large_standard"
    assert unit["eligible"] is True
    assert unit["split_2_3"] is None
    assert unit["split_2_3_disabled"] is True
    assert unit["split_2_3_disabled_reason"] == SPLIT_DISABLED_REASON_STANDARD


def test_small_oversize_has_split_option():
    unit = compute_unit_placement_fees(60, 45, 35, 5.0)
    assert unit["size_class"] == "small_oversize"
    assert unit["eligible"] is True
    assert unit["split_2_3"] is not None
    assert unit["split_2_3_disabled"] is False


def test_weight_only_fallback_large_standard():
    unit = compute_unit_placement_fees(0, 0, 0, 2.0)
    assert unit["size_class"] == "large_standard"
    assert unit["billing_lb"] == round(kg_to_lb(2.0), 3)
    assert unit["volume_weight_applied"] is False


def test_shipment_split_disabled_for_standard_only():
    rows = [
        {
            "SKU简称": "STD",
            "发货总数": 10,
            "unit_length_cm": 40,
            "unit_width_cm": 30,
            "unit_height_cm": 20,
            "unit_weight_kg": 0.5,
        }
    ]
    res = compute_shipment_placement_fees(rows)
    assert res["split_2_3"]["enabled"] is False
    assert res["split_2_3"]["disabled_reason"] == SPLIT_DISABLED_REASON_STANDARD
    assert res["one_location"]["min_usd"] > 0


def test_shipment_split_enabled_for_oversize():
    rows = [
        {
            "SKU简称": "OS",
            "发货总数": 5,
            "unit_length_cm": 60,
            "unit_width_cm": 45,
            "unit_height_cm": 35,
            "unit_weight_kg": 5.0,
        }
    ]
    res = compute_shipment_placement_fees(rows)
    assert res["split_2_3"]["enabled"] is True
    assert res["line_items"][0]["subtotal_split_2_3"] is not None


def test_large_standard_fee_tier():
    fees = _engine.lookup_fees("large_standard", 0.5)
    assert fees is not None
    assert fees["1_loc"] == (0.20, 0.40)
    assert fees["5_loc"] == (0.0, 0.0)


def test_classify_placement_scenario():
    assert classify_placement_scenario(1) == "one_location"
    assert classify_placement_scenario(3) == "split_2_3"
    assert classify_placement_scenario(5) == "optimized_5"


def test_locked_fee_one_warehouse():
    rows = [
        {
            "SKU简称": "STD",
            "发货总数": 10,
            "unit_length_cm": 40,
            "unit_width_cm": 30,
            "unit_height_cm": 20,
            "unit_weight_kg": 0.5,
        }
    ]
    locked = compute_locked_placement_fee(rows, ["RDU2"])
    assert locked["actual_location_count"] == 1
    assert locked["scenario"] == "one_location"
    assert locked["locked_usd"] == locked["applicable_range_max_usd"]
    assert locked["locked_usd"] >= locked["applicable_range_min_usd"]


def test_locked_fee_three_warehouses_standard_forced():
    rows = [
        {
            "SKU简称": "STD",
            "发货总数": 10,
            "unit_length_cm": 40,
            "unit_width_cm": 30,
            "unit_height_cm": 20,
            "unit_weight_kg": 0.5,
        }
    ]
    locked = compute_locked_placement_fee(rows, ["GYR2", "FWA4", "MDW2"])
    assert locked["actual_location_count"] == 3
    assert locked["scenario"] == "one_location_forced"
    assert "美西" in locked["warehouse_regions"] or "美中" in locked["warehouse_regions"]


def test_locked_fee_five_warehouses_free():
    rows = [
        {
            "SKU简称": "STD",
            "发货总数": 10,
            "unit_length_cm": 40,
            "unit_width_cm": 30,
            "unit_height_cm": 20,
            "unit_weight_kg": 0.5,
        }
    ]
    locked = compute_locked_placement_fee(rows, ["A", "B", "C", "D", "E"])
    assert locked["scenario"] == "optimized_5"
    assert locked["locked_usd"] == 0.0


if __name__ == "__main__":
    test_large_standard_no_split_option()
    test_small_oversize_has_split_option()
    test_weight_only_fallback_large_standard()
    test_shipment_split_disabled_for_standard_only()
    test_shipment_split_enabled_for_oversize()
    test_large_standard_fee_tier()
    test_classify_placement_scenario()
    test_locked_fee_one_warehouse()
    test_locked_fee_three_warehouses_standard_forced()
    test_locked_fee_five_warehouses_free()
    print("ALL OK")
