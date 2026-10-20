"""产品信息总表正则解析单元测试。"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest

from fba_tool.product_master_parser import (
    _compact_header,
    _find_header_row,
    _pick_customs_name_column,
    _pick_model_name_column,
    parse_business_product_master,
)

PET_COURTYARD_FIXTURE = (
    Path(__file__).resolve().parent
    / "tests"
    / "fixtures"
    / "product-info"
    / "宠物庭院-产品信息表(仅内部人员使用).xlsx"
)


def test_compact_header_strips_newlines():
    assert _compact_header("SKU\n(升序...)") == "SKU(升序...)"
    assert _compact_header("美国海关编码\r\n*") == "美国海关编码*"


def test_pick_customs_name_prefers_customs_column():
    cols = ["SKU", "中文名称(型号)", "商品报关名称", "产品名称"]
    assert _pick_customs_name_column(cols) == "商品报关名称"
    assert _pick_model_name_column(cols) == "中文名称(型号)"


def test_find_header_row_skips_title_rows():
    df = pd.DataFrame(
        [
            ["产品信息总表", "", ""],
            ["SKU\n(必填)", "产品名称", "商品报关名称"],
            ["ABC-001", "Pet Bed", "宠物垫"],
        ]
    )
    assert _find_header_row(df) == 1


def test_parse_csv_with_dirty_headers():
    csv = (
        '"SKU\n(升序)","产品名称","商品报关名称","美国海关编码","材质","售价(客户到手价格)"\n'
        '"ABC-001","Pet Bed Mat","宠物垫","3926909090","涤纶","12.5"\n'
        '"运营部分填写","","","","",""\n'
    )
    records, col_map = parse_business_product_master(csv.encode("utf-8-sig"), "产品信息.csv")
    assert len(records) == 1
    rec = records[0]
    assert rec["sku"] == "ABC-001"
    assert rec["english_name"] == "Pet Bed Mat"
    assert rec["chinese_name"] == "宠物垫"
    assert rec["hs_code"] == "3926909090"
    assert rec["material"] == "涤纶"
    assert rec["declared_value"] == 12.5
    assert "sku" in col_map


def test_parse_excel_skips_trademark_sheet():
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        pd.DataFrame([["商标信息"], ["BRAND-X"]]).to_excel(writer, sheet_name="商标", index=False, header=False)
        pd.DataFrame(
            [
                ["SKU", "产品名称", "中文名称(型号)", "商品报关名称"],
                ["SKU-X", "Name EN", "型号名", "报关名"],
            ]
        ).to_excel(writer, sheet_name="产品信息", index=False, header=False)
    records, col_map = parse_business_product_master(bio.getvalue(), "master.xlsx")
    assert len(records) == 1
    assert records[0]["sku"] == "SKU-X"
    assert records[0]["chinese_name"] == "报关名"
    assert records[0]["model_name"] == "型号名"
    assert col_map["chinese_name"] == "商品报关名称"
    assert col_map["model_name"] == "中文名称(型号)"


def test_sku_read_as_string_not_scientific():
    csv = "SKU,产品名称\n1.23E+10,Test\n"
    records, _ = parse_business_product_master(csv.encode(), "t.csv")
    assert records[0]["sku"] == "12300000000"


def test_extra_data_aligns_after_sku_row_filter():
    """未映射列 extra_data 须与过滤后有效 SKU 行数一致（避免 38 vs 34 报错）。"""
    rows = [["SKU", "产品名称", "备注列"]]
    rows.extend([[f"SKU-{i}", f"Product {i}", f"extra{i}"] for i in range(34)])
    rows.extend([["", "empty sku", "x"], ["填写说明", "bad", "x"], ["", "", ""], ["即将淘汰", "bad2", "x"]])
    bio = io.BytesIO()
    pd.DataFrame(rows).to_excel(bio, index=False, header=False)
    records, _ = parse_business_product_master(bio.getvalue(), "t.xlsx")
    assert len(records) == 34
    assert records[0]["extra_data"]


@pytest.mark.skipif(not PET_COURTYARD_FIXTURE.is_file(), reason="fixture xlsx not present")
def test_parse_pet_courtyard_product_info_fixture():
    """回归：宠物庭院内部产品信息总表（可持续更新同路径文件）。"""
    raw = PET_COURTYARD_FIXTURE.read_bytes()
    records, col_map = parse_business_product_master(raw, PET_COURTYARD_FIXTURE.name)
    skus = [r["sku"] for r in records]

    assert col_map["chinese_name"] == "商品报关名称"
    assert col_map.get("model_name") == "中文名称(型号)"
    assert len(records) >= 25
    assert not any("表格" in s or "填充" in s for s in skus)

    barrier = next((r for r in records if r["sku"] == "J-PETBARRIERS-FBA"), None)
    if barrier:
        assert barrier["chinese_name"] == "车载狗栏"
        assert barrier["model_name"] == "车载金属狗栏"
        assert barrier["english_name"] == "车载金属狗栏"
        assert barrier["hs_code"] == "9403200000"
