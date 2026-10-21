"""PR-0：合成箱唛 PDF 必须能被 shipment_parser.parse_pdf_pages 解析。

版面按方案第 0 章：pymupdf 文本型 PDF，每页一个箱唛。
SKU 用 TEST_*，箱号用 FBATEST，不使用真实货件号。
"""
from __future__ import annotations

import fitz

from fba_tool.shipment_parser import parse_pdf_pages


def _pdf(pages: list[str]) -> bytes:
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def test_labeled_page_parses_box_qty_and_warehouse():
    raw = _pdf(
        [
            "\n".join(
                [
                    "FBATEST00001U000001",
                    "CLT2",
                    "10240 Old Dowd Rd, Charlotte, NC",
                    "SKU: TEST_A",
                    "Qty: 10",
                ]
            )
        ]
    )
    pages = parse_pdf_pages(raw)
    assert len(pages) == 1
    page = pages[0]
    assert page.fba_box_id == "FBATEST00001U000001"
    assert page.box_no == 1
    assert page.shipment_id == "FBATEST00001"
    assert page.qty == 10
    assert page.warehouse_code == "CLT2"
    assert "Old Dowd Rd" in page.raw_text
    assert "TEST_A" in page.raw_text


def test_mixed_sku_page_is_flagged():
    raw = _pdf(
        [
            "\n".join(
                [
                    "FBATEST00001U000002",
                    "LAS1",
                    "10240 Old Dowd Rd, Charlotte, NC",
                    "Mixed SKUs",
                    "Qty: 4",
                ]
            )
        ]
    )
    pages = parse_pdf_pages(raw)
    assert len(pages) == 1
    assert pages[0].is_mixed is True
    assert pages[0].fba_box_id == "FBATEST00001U000002"
    assert pages[0].sku == ""


def test_page_without_sku_or_qty_text_still_parses_box():
    raw = _pdf(
        [
            "\n".join(
                [
                    "FBATEST00002U000001",
                    "LAX9",
                    "10240 Old Dowd Rd, Charlotte, NC",
                ]
            )
        ]
    )
    pages = parse_pdf_pages(raw)
    assert len(pages) == 1
    page = pages[0]
    assert page.fba_box_id == "FBATEST00002U000001"
    assert page.sku == ""
    assert page.qty == 0
    assert page.warehouse_code == "LAX9"
