"""三维交叉校验单元测试。"""
import pandas as pd

from fba_tool.shipment_cross_check import (
    build_worker_packing_rows,
    check_declared_box_specs,
    validate_step1_macro_totals,
)
from fba_tool.shipment_parser import format_box_u_label


def test_format_box_u_label():
    assert format_box_u_label(5) == "U005"


def test_macro_total_mismatch():
    from fba_tool.shipment_validator import ShipmentPair
    from fba_tool.shipment_parser import CsvShipment

    csv = CsvShipment(
        shipment_id="FBA1",
        warehouse_code="RDU2",
        box_count=1,
        box_data={1: {"SKU-A": 5}},
    )
    pair = ShipmentPair("FBA1", "RDU2", csv, None)  # type: ignore[arg-type]
    errors = validate_step1_macro_totals([pair], [{"SKU简称": "SKU-A", "发货总数": 10}])
    assert errors
    assert "宏观数量不符" in errors[0]


def test_worker_packing_rows_structure():
    from fba_tool.shipment_validator import ShipmentPair
    from fba_tool.shipment_parser import CsvShipment

    csv = CsvShipment(
        shipment_id="FBA1",
        warehouse_code="FWA4",
        box_count=1,
        box_data={1: {"SKU-A": 3}},
        box_fba_ids={1: "FBA1U000001"},
    )
    pair = ShipmentPair("FBA1", "FWA4", csv, None)  # type: ignore[arg-type]
    rows = build_worker_packing_rows([pair])
    types = [r["row_type"] for r in rows]
    assert "warehouse_header" in types
    assert "box_header" in types
    assert "item" in types


def _pair_with_specs(weight_kg: float, dims=(40.0, 30.0, 30.0)):
    from fba_tool.shipment_parser import CsvShipment
    from fba_tool.shipment_validator import ShipmentPair

    l, w, h = dims
    csv = CsvShipment(
        shipment_id="FBA1",
        warehouse_code="FWA4",
        box_count=1,
        box_data={1: {"SKU-A": 10}},
        box_fba_ids={1: "FBA1U000001"},
        box_specs=pd.DataFrame(
            [
                {
                    "仓库代码": "FWA4",
                    "箱号": 1,
                    "长(cm)": l,
                    "宽(cm)": w,
                    "高(cm)": h,
                    "实重(kg)": weight_kg,
                    "FBA箱号": "FBA1U000001",
                }
            ]
        ),
    )
    return ShipmentPair("FBA1", "FWA4", csv, None)  # type: ignore[arg-type]


def _local_metrics(gross_kg: float, volume_cm3: float = 40.0 * 30.0 * 30.0):
    return pd.DataFrame([{"箱号": 1, "毛重(kg)": gross_kg, "体积(cm3)": volume_cm3}])


class _Match:
    """最小化的 BoxLabelMatch 替身。"""

    def __init__(self):
        self.shipment_id = "FBA1"
        self.amazon_box_no = 1
        self.local_box_no = 1
        self.local_box_label = "Box-01"


def test_declared_specs_matching_plan_pass_silently():
    check = check_declared_box_specs([_pair_with_specs(20.5)], _local_metrics(20.5), [_Match()])
    assert check["ok"] is True
    assert check["warnings"] == []
    assert check["compared_boxes"] == 1


def test_declared_weight_mismatch_is_flagged():
    """申报 12kg 实际方案 20.5kg → 亚马逊复磅后收重量差异费。"""
    check = check_declared_box_specs([_pair_with_specs(12.0)], _local_metrics(20.5), [_Match()])
    assert check["ok"] is False
    kinds = {r["kind"] for r in check["rows"]}
    assert "weight" in kinds
    assert any("申报箱重不符" in w for w in check["warnings"])


def test_declared_volume_mismatch_is_flagged():
    pair = _pair_with_specs(20.5, dims=(60.0, 40.0, 40.0))
    check = check_declared_box_specs([pair], _local_metrics(20.5), [_Match()])
    assert any(r["kind"] == "volume" for r in check["rows"])


def test_total_weight_checked_without_box_mapping():
    """亚马逊主导模式下没有逐箱映射，总量偏差仍须暴露。"""
    check = check_declared_box_specs([_pair_with_specs(5.0)], _local_metrics(20.5), None)
    assert check["compared_boxes"] == 0
    assert any(r["kind"] == "total_weight" for r in check["rows"])


def test_no_specs_or_no_plan_is_silent():
    from fba_tool.shipment_parser import CsvShipment
    from fba_tool.shipment_validator import ShipmentPair

    bare_csv = CsvShipment(shipment_id="FBA1", warehouse_code="FWA4", box_count=0)
    bare = ShipmentPair("FBA1", "FWA4", bare_csv, None)  # type: ignore[arg-type]
    assert check_declared_box_specs([bare], _local_metrics(20.5), None)["warnings"] == []
    assert check_declared_box_specs([_pair_with_specs(20.5)], None, None)["warnings"] == []


if __name__ == "__main__":
    test_format_box_u_label()
    test_macro_total_mismatch()
    test_worker_packing_rows_structure()
    test_declared_specs_matching_plan_pass_silently()
    test_declared_weight_mismatch_is_flagged()
    test_declared_volume_mismatch_is_flagged()
    test_total_weight_checked_without_box_mapping()
    test_no_specs_or_no_plan_is_silent()
    print("ALL OK")
