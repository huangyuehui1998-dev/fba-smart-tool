"""table_loader 全格式路由单元测试。"""
from __future__ import annotations

import io

import pandas as pd
import pytest

from fba_tool.master_data_parser import parse_master_report
from fba_tool.product_master_parser import parse_business_product_master
from fba_tool.table_loader import (
    detect_table_format,
    load_raw_table,
    supported_upload_extensions,
)


def test_supported_extensions():
    exts = set(supported_upload_extensions())
    assert {"xlsx", "xlsm", "xls", "xlsb", "csv", "tsv", "txt"} <= exts


def test_detect_zip_magic_overrides_csv_extension():
    bio = io.BytesIO()
    pd.DataFrame([["SKU", "产品名称"], ["A-1", "Name"]]).to_excel(bio, index=False, header=False)
    data = bio.getvalue()
    assert detect_table_format(data, "wrong.csv") == "xlsx"


def test_load_csv_raw_grid():
    csv = "SKU,产品名称\nA-1,Pet\n"
    df = load_raw_table(csv.encode("utf-8-sig"), "t.csv")
    assert list(df.iloc[0]) == ["SKU", "产品名称"]
    assert df.iloc[1, 0] == "A-1"


def test_load_tsv_raw_grid():
    tsv = "SKU\t产品名称\nA-2\tMat\n"
    df = load_raw_table(tsv.encode(), "t.tsv")
    assert df.shape[1] == 2
    assert df.iloc[1, 0] == "A-2"


def test_load_txt_tab_separated():
    text = "SKU\tASIN\nSKU-3\tB001\n"
    df = load_raw_table(text.encode(), "report.txt")
    assert df.iloc[1, 1] == "B001"


def test_load_xlsx_xlsm_raw_grid():
    for ext in ("xlsx", "xlsm"):
        bio = io.BytesIO()
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            pd.DataFrame([["SKU", "名"], ["X-1", "n"]]).to_excel(
                writer, sheet_name="Sheet1", index=False, header=False
            )
        df = load_raw_table(bio.getvalue(), f"t.{ext}")
        assert df.iloc[0, 0] == "SKU"


def test_product_master_via_loader_dirty_csv():
    csv = (
        '"SKU\n(升序)","产品名称","商品报关名称"\n'
        '"SKU-ROUTE","EN","中文"\n'
    )
    records, _ = parse_business_product_master(csv.encode("utf-8-sig"), "产品.csv")
    assert records[0]["sku"] == "SKU-ROUTE"
    assert records[0]["chinese_name"] == "中文"


def test_fee_preview_xlsx_via_master_parser():
    bio = io.BytesIO()
    pd.DataFrame(
        [
            ["sku", "asin", "longest-side", "median-side", "shortest-side", "item-package-weight"],
            ["SKU-XLSX", "B001", "10", "8", "6", "2.20462"],
        ]
    ).to_excel(bio, index=False, header=False)
    rows = parse_master_report(bio.getvalue(), "fee_preview", "fee_preview.xlsx")
    assert len(rows) == 1
    assert rows[0]["sku"] == "SKU-XLSX"
    assert rows[0]["unit_length"] is not None


def test_load_xls_if_xlwt_available():
    xlwt = pytest.importorskip("xlwt")
    bio = io.BytesIO()
    book = xlwt.Workbook()
    sheet = book.add_sheet("Sheet1")
    sheet.write(0, 0, "SKU")
    sheet.write(0, 1, "产品名称")
    sheet.write(1, 0, "LEGACY-1")
    sheet.write(1, 1, "Legacy")
    book.save(bio)
    df = load_raw_table(bio.getvalue(), "legacy.xls")
    assert df.iloc[1, 0] == "LEGACY-1"


def test_unknown_format_raises():
    with pytest.raises(ValueError, match="暂不支持的文件格式"):
        load_raw_table(b"\x00\x01\x02\x03", "data.bin")
