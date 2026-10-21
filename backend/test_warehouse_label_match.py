"""P0-2 / P0-6：箱唛仓码不从街道名猜，交叉校验拦住 Mixed、空 SKU 和重复箱唛。"""
from __future__ import annotations

import fitz

from fba_tool.master_db import init_master_db
from fba_tool.shipment_cross_check import cross_validate_pair
from fba_tool.shipment_parser import (
    CsvShipment,
    PdfBoxPage,
    parse_pdf_pages,
    resolve_warehouse_with_warnings,
    warehouse_from_label_text,
)


def _pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def test_explicit_code_beats_dowd_street():
    raw = _pdf("FBATEST00001U000001\nCLT2\n10240 Old Dowd Rd, Charlotte, NC\nSKU: TEST_A\nQty: 10\n")
    pages = parse_pdf_pages(raw)
    assert pages[0].warehouse_code == "CLT2"
    assert pages[0].warehouse_code != "DOWD"


def test_address_library_match_and_no_guess(monkeypatch, tmp_path):
    ad = tmp_path / "app_data"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    init_master_db()
    text = "FBATEST00001U000001\n10240 Old Dowd Rd, Charlotte, NC\n"
    code, warnings = warehouse_from_label_text(text)
    assert code == ""
    assert warnings
    assert "DOWD" not in code

    from fba_tool.master_db import _connect

    with _connect() as conn:
        conn.execute(
            """INSERT INTO fba_warehouse
               (code, name, company, address1, address2, address3, city, state, zip, country, region, phone, source, updated_at)
               VALUES ('CLT2', '', '', '10240 Old Dowd Rd', '', '', 'Charlotte', 'NC', '28214', 'US', '', '', 'test', '2026-10-20')"""
        )
        conn.commit()
    code, warnings = warehouse_from_label_text(text)
    assert code == "CLT2"
    assert warnings == []


def test_dowd_pages_do_not_outvote_csv_clt2():
    page = PdfBoxPage(0, "FBATEST0001", "FBATEST0001U000001", 1, warehouse_code="DOWD")
    code, warnings = resolve_warehouse_with_warnings("CLT2", "x.pdf", [page] * 32)
    assert code == "CLT2"
    assert all("DOWD" not in item for item in warnings)


def _csv():
    return CsvShipment(
        "FBATEST0001",
        "CLT2",
        1,
        box_data={1: {"TEST_A": 10}},
        box_fba_ids={1: "FBATEST0001U000001"},
    )


def test_single_sku_csv_rejects_mixed_label():
    errors = cross_validate_pair(
        _csv(),
        [PdfBoxPage(0, "FBATEST0001", "FBATEST0001U000001", 1, is_mixed=True)],
        "CLT2",
        "FBATEST0001",
    )
    assert any("Mixed" in item for item in errors)


def test_unrecognized_label_sku_is_an_error():
    errors = cross_validate_pair(
        _csv(),
        [PdfBoxPage(0, "FBATEST0001", "FBATEST0001U000001", 1)],
        "CLT2",
        "FBATEST0001",
    )
    assert any("未识别" in item for item in errors)


def test_duplicate_labels_are_an_error():
    pages = [PdfBoxPage(i, "FBATEST0001", "FBATEST0001U000001", 1, sku="TEST_A", qty=10) for i in range(2)]
    errors = cross_validate_pair(_csv(), pages, "CLT2", "FBATEST0001")
    assert any("重复" in item for item in errors)
