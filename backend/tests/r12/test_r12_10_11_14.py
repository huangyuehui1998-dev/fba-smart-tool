"""R12-10 折行 SKU，R12-11 仓码不回写 DOWD，R12-14 缺 PDF / 重复箱唛。"""
from __future__ import annotations

import fitz

from fba_tool.shipment_cross_check import cross_validate_pair
from fba_tool.shipment_parser import CsvShipment, PdfBoxPage, join_wrapped_sku, parse_pdf_pages
from fba_tool.shipment_validator import validate_shipments

_WRAPPED = "J-PETMAT-CAR-ZHENTOU-1PC-FBA"


def _csv_bytes() -> bytes:
    text = "\n".join(
        [
            "货件编号,FBATEST0001",
            "货件名称,CLT2 shipment",
            "箱子数量,1",
            "SKU,FNSKU,箱子1",
            "TEST_A,X00TEST567,10",
            "箱号,,FBATEST0001U000001",
        ]
    )
    return text.encode("utf-8")


def test_wrapped_single_sku_is_joined():
    text = f"Single SKU\nJ-PETMAT-CAR-ZHENTOU-\n1PC-FBA\nQty: 4\n"
    assert join_wrapped_sku(text) == _WRAPPED
    csv = CsvShipment(
        "FBATEST0001",
        "CLT2",
        1,
        box_data={1: {_WRAPPED: 4}},
        box_fba_ids={1: "FBATEST0001U000001"},
    )
    page = PdfBoxPage(
        0,
        "FBATEST0001",
        "FBATEST0001U000001",
        1,
        qty=4,
        raw_text=text,
    )
    errors = cross_validate_pair(csv, [page], "CLT2", "FBATEST0001")
    assert not any(item.startswith("❌") for item in errors)
    assert not any("箱唛 SKU 未识别" in item for item in errors)


def test_missing_sku_uses_fnsku_or_qty_as_warning_only():
    csv = CsvShipment(
        "FBATEST0001",
        "CLT2",
        1,
        box_data={1: {"TEST_A": 10}},
        box_fba_ids={1: "FBATEST0001U000001"},
        sku_fnsku={"TEST_A": "X00TEST567"},
    )
    warned = cross_validate_pair(
        csv,
        [PdfBoxPage(0, "FBATEST0001", "FBATEST0001U000001", 1, fnsku="X00TEST567", qty=10)],
        "CLT2",
        "FBATEST0001",
    )
    assert any("箱唛 SKU 未识别，已按 FNSKU/数量核对" in item for item in warned)
    assert not any(item.startswith("❌") for item in warned)

    blank = cross_validate_pair(
        csv,
        [PdfBoxPage(0, "FBATEST0001", "FBATEST0001U000001", 1)],
        "CLT2",
        "FBATEST0001",
    )
    assert any(item.startswith("❌") and "都识别不出" in item for item in blank)


def test_duplicate_page_names_the_box_and_missing_pdf_is_a_hard_error():
    csv = CsvShipment(
        "FBATEST0001",
        "CLT2",
        1,
        box_data={1: {"TEST_A": 10}},
        box_fba_ids={1: "FBATEST0001U000001"},
    )
    pages = [
        PdfBoxPage(i, "FBATEST0001", "FBATEST0001U000001", 1, sku="TEST_A", qty=10) for i in range(2)
    ]
    errors = cross_validate_pair(csv, pages, "CLT2", "FBATEST0001")
    assert any("U000001 出现 2 页" in item for item in errors)

    result = validate_shipments([("CL2.csv", _csv_bytes())], [])
    assert result.ok is False
    assert result.status_lines[-1].startswith("❌")
    assert all("交叉校验通过" not in line for line in result.status_lines)


def test_dowd_stays_out_of_the_warehouse_field():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "FBATEST00001U000001\nCLT2\n10240 Old Dowd Rd\nSingle SKU\nTEST_A\nQty: 10\n")
    raw = doc.tobytes()
    doc.close()
    parsed = parse_pdf_pages(raw)[0]
    assert parsed.warehouse_code == "CLT2"
    assert "DOWD" in parsed.ignored_tokens
    public = {"warehouse_code": parsed.warehouse_code, "sku": parsed.sku, "fnsku": parsed.fnsku}
    assert "DOWD" not in str(public)
