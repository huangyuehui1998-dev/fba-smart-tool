"""货件编号匹配与真实箱号重排测试。"""
from pathlib import Path

from fba_tool.shipment_parser import parse_csv_shipment, parse_pdf_shipment
from fba_tool.shipment_validator import compare_box_data, validate_shipments


def test_column_mapping_not_sequential():
    csv_path = Path("templates/亚马逊FBA表1.csv")
    if not csv_path.exists():
        return
    ship = parse_csv_shipment(csv_path.read_bytes())
    assert ship.shipment_id == "FBA19F4BDYRN"
    assert ship.warehouse_code == "RDU2"
    # 第一列「箱子1」应对应真实箱号 11，而非 1
    first_cols = sorted(ship.column_to_box.items())[:3]
    assert 11 in ship.column_to_box.values()
    assert ship.box_data[11]["J-PETWOODSTAIRS-HUI-4PCS-FBA"] == 3


def test_pdf_shipment_id_and_box():
    pdf_path = Path("templates/箱唛1-RDU2.pdf")
    if not pdf_path.exists():
        return
    ship = parse_pdf_shipment(pdf_path.read_bytes())
    assert ship.shipment_id == "FBA19F4BDYRN"
    assert ship.page_count == 27
    assert 1 in ship.box_data


def test_full_batch_validation():
    tpl = Path("templates")
    csv_payload = [(f.name, f.read_bytes()) for f in sorted(tpl.glob("亚马逊FBA表[1-9].csv"))]  # S8 D12：排除重复票和产品信息表
    pdf_payload = [(f.name, f.read_bytes()) for f in sorted(tpl.glob("*.pdf"))]
    if not csv_payload or not pdf_payload:
        return
    result = validate_shipments(csv_payload, pdf_payload)
    assert result.ok, result.errors


if __name__ == "__main__":
    test_column_mapping_not_sequential()
    test_pdf_shipment_id_and_box()
    test_full_batch_validation()
    print("ALL OK")
