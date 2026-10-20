"""产品主数据库：单品/外箱分离、单位换算、Nullable 字段测试。"""
import pytest

from fba_tool.master_db import get_product_by_sku, init_master_db, upsert_product
from fba_tool.master_data_apply import (
    apply_master_to_input_rows,
    build_placement_unit_rows,
    resolve_sku_master_flags,
)
from fba_tool.master_data_parser import parse_master_report
from fba_tool.units import LB_TO_KG
from fba_tool.volume_weight import to_cm, to_kg


@pytest.fixture(autouse=True)
def isolated_app_data(monkeypatch, tmp_path):
    ad = tmp_path / "app_data"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    init_master_db()
    return ad


def test_inch_lb_to_cm_kg():
    assert to_cm(10.0, "in") == round(10 * 2.54, 1)
    assert to_kg(1.0, "lb") == round(1.0 * LB_TO_KG, 2)


def test_fee_preview_parsed_as_unit_dims():
    csv = (
        "sku,asin,fnsku,longest-side,median-side,shortest-side,"
        "item-package-weight,unit-of-dimension,unit-of-weight\n"
        "SKU-US,B001,FNSKU1,10.0,8.0,6.0,1.0,inches,pounds\n"
    )
    rows = parse_master_report(csv.encode(), "fee_preview")
    assert len(rows) == 1
    r = rows[0]
    assert r["unit_length"] == to_cm(10.0, "in")
    assert r["unit_width"] == to_cm(8.0, "in")
    assert r["unit_height"] == to_cm(6.0, "in")
    assert r["unit_weight"] == to_kg(1.0, "lb")
    assert "carton_length" not in r


def test_inventory_only_codes_no_dims():
    tsv = (
        "Seller-SKU\tASIN1\tFulfillment-Channel-SKU\tItem-Length\tItem-Width\tItem-Height\t"
        "Item-Weight\tItem-Length-Unit-of-Measure\tItem-Weight-Unit-of-Measure\n"
        "SKU-EU\tB002\tFNSKU2\t30.0\t20.0\t10.0\t1.5\tCentimeters\tKilograms\n"
    )
    rows = parse_master_report(tsv.encode(), "inventory")
    assert len(rows) == 1
    r = rows[0]
    assert r["sku"] == "SKU-EU"
    assert r["asin"] == "B002"
    assert "unit_length" not in r


def test_fee_preview_does_not_override_carton_in_step1():
    init_master_db()
    upsert_product(
        {
            "sku": "SEP-SKU",
            "asin": "B001",
            "fnsku": "F001",
            "unit_length": 10.0,
            "unit_width": 8.0,
            "unit_height": 6.0,
            "unit_weight": 0.5,
        }
    )
    input_row = {
        "SKU简称": "SEP-SKU",
        "FNSKU": "",
        "发货总数": 100,
        "单箱装量": 10,
        "箱长(cm)": 45,
        "箱宽(cm)": 32,
        "箱高(cm)": 28,
        "单个重量(kg)": 0.5,
        "空纸箱重(kg)": 0.2,
        "单箱毛重(kg)": None,
    }
    merged, sources = apply_master_to_input_rows([input_row])
    assert merged[0]["FNSKU"] == "F001"
    assert merged[0]["箱长(cm)"] == 45
    assert merged[0]["箱宽(cm)"] == 32
    assert merged[0]["箱高(cm)"] == 28
    assert sources[0] == "manual"

    placement = build_placement_unit_rows([input_row])
    assert placement[0]["unit_length_cm"] == 10.0
    assert placement[0]["unit_width_cm"] == 8.0
    assert placement[0]["unit_height_cm"] == 6.0


def test_carton_from_master_fills_empty_only():
    init_master_db()
    upsert_product(
        {
            "sku": "CARTON-SKU",
            "fnsku": "F999",
            "carton_length": 50.0,
            "carton_width": 40.0,
            "carton_height": 30.0,
            "qty_per_box": 12,
        }
    )
    filled, filled_src = apply_master_to_input_rows(
        [
            {
                "SKU简称": "CARTON-SKU",
                "FNSKU": "",
                "发货总数": 10,
                "单箱装量": 5,
                "箱长(cm)": 10,
                "箱宽(cm)": 10,
                "箱高(cm)": 10,
                "单个重量(kg)": 0.3,
                "空纸箱重(kg)": 0.1,
                "单箱毛重(kg)": None,
            }
        ]
    )
    assert filled[0]["箱长(cm)"] == 10
    assert filled[0]["单箱装量"] == 5
    assert filled_src[0] == "manual"

    empty, empty_src = apply_master_to_input_rows(
        [
            {
                "SKU简称": "CARTON-SKU",
                "FNSKU": "",
                "发货总数": 10,
                "单箱装量": "",
                "箱长(cm)": "",
                "箱宽(cm)": "",
                "箱高(cm)": "",
                "单个重量(kg)": 0.3,
                "空纸箱重(kg)": 0.1,
                "单箱毛重(kg)": None,
            }
        ]
    )
    assert empty[0]["箱长(cm)"] == 50.0
    assert empty[0]["箱宽(cm)"] == 40.0
    assert empty[0]["箱高(cm)"] == 30.0
    assert empty[0]["单箱装量"] == 12
    assert empty_src[0] == "official"
    assert resolve_sku_master_flags(["CARTON-SKU"])["CARTON-SKU"] == "official"


def test_upsert_preserves_unit_when_second_report_is_codes_only():
    init_master_db()
    upsert_product(
        {
            "sku": "MERGE-SKU",
            "unit_length": 30.0,
            "unit_width": 20.0,
            "unit_height": 10.0,
            "unit_weight": 1.2,
        }
    )
    upsert_product({"sku": "MERGE-SKU", "asin": "B999", "fnsku": "F999"})
    rec = get_product_by_sku("MERGE-SKU")
    assert rec["asin"] == "B999"
    assert rec["unit_length"] == 30.0
    assert rec["unit_weight"] == 1.2


def test_invoice_fields_upsert_and_patch():
    from fba_tool.master_db import patch_product_field

    init_master_db()
    upsert_product(
        {
            "sku": "INV-SKU",
            "chinese_name": "宠物垫",
            "english_name": "Pet Mat",
            "hs_code": "3926909090",
            "declared_value": 9.99,
        }
    )
    rec = get_product_by_sku("INV-SKU")
    assert rec["chinese_name"] == "宠物垫"
    assert rec["hs_code"] == "3926909090"
    assert rec["declared_value"] == 9.99

    patched = patch_product_field("INV-SKU", "material", "涤纶")
    assert patched["material"] == "涤纶"
    assert patched["chinese_name"] == "宠物垫"


def test_qty_per_box_persists():
    """qty_per_box 曾在 INSERT 列清单中缺失，导致《产品信息总表》的单箱装量静默丢失。"""
    from fba_tool.master_db import patch_product_field

    init_master_db()
    upsert_product({"sku": "QPB-SKU", "chinese_name": "整箱装", "qty_per_box": 24})
    assert get_product_by_sku("QPB-SKU")["qty_per_box"] == 24

    assert patch_product_field("QPB-SKU", "qty_per_box", 36)["qty_per_box"] == 36
    assert get_product_by_sku("QPB-SKU")["qty_per_box"] == 36

    # 后续只带编码的上传不得抹掉已有值
    upsert_product({"sku": "QPB-SKU", "asin": "B123"})
    assert get_product_by_sku("QPB-SKU")["qty_per_box"] == 36


if __name__ == "__main__":
    test_inch_lb_to_cm_kg()
    test_fee_preview_parsed_as_unit_dims()
    test_inventory_only_codes_no_dims()
    test_fee_preview_does_not_override_carton_in_step1()
    test_carton_from_master_marks_official()
    test_upsert_preserves_unit_when_second_report_is_codes_only()
    print("ALL OK")
