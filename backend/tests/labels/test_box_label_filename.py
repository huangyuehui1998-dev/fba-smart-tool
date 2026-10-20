"""箱唛 PDF 文件名解析测试。"""
from fba_tool.box_label_filename import (
    chinese_numeral_to_int,
    column_label_for_pair,
    parse_box_label_pdf_name,
    sort_pairs_by_box_label_pdf,
)
from fba_tool.shipment_validator import ShipmentPair


def test_parse_user_filename():
    name = "第二票外箱贴US-7TH-9810-PETBEDMAT-FBA19GQW64C7-SCK4.pdf"
    meta = parse_box_label_pdf_name(name)
    assert meta.ticket_prefix == "第二票"
    assert meta.ticket_num == 2
    assert meta.warehouse == "SCK4"
    assert meta.shipment_id == "FBA19GQW64C7"


def test_sort_by_ticket_in_filename():
    pairs = [
        ShipmentPair("FBA3", "GYR2", None, None, "第五票外箱贴X-FBA3-GYR2.pdf"),  # type: ignore[arg-type]
        ShipmentPair("FBA1", "SCK4", None, None, "第二票外箱贴US-7TH-FBA1-SCK4.pdf"),  # type: ignore[arg-type]
        ShipmentPair("FBA2", "FWA4", None, None, "第一票外箱贴Y-FBA2-FWA4.pdf"),  # type: ignore[arg-type]
    ]
    ordered = sort_pairs_by_box_label_pdf(pairs)
    labels = [column_label_for_pair(p, i) for i, p in enumerate(ordered, 1)]
    assert labels == ["第一票 FWA4", "第二票 SCK4", "第五票 GYR2"]


def test_chinese_numeral():
    assert chinese_numeral_to_int("二") == 2
    assert chinese_numeral_to_int("十一") == 11


if __name__ == "__main__":
    test_parse_user_filename()
    test_sort_by_ticket_in_filename()
    test_chinese_numeral()
    print("ALL OK")
