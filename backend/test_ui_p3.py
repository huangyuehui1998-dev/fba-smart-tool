"""PR-3：STA 预检、四文件 zip、仓码冲突、费用文案。"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

from fba_tool.placement_fee import PlacementFeeEngine
from fba_tool.shipment_validator import warehouse_conflict
from fba_tool.sta_precheck import load_sta_dropdowns, precheck_sta_rows
from main import app

ROOT = Path(__file__).resolve().parents[1]
DROPDOWN = ROOT / "backend" / "config" / "sta_dropdowns.default.json"


def _header():
    return ["SKU", "商品名称", "ASIN", "FNSKU", "状况", "预处理类型", "商品预处理方是谁？", "商品贴标方是谁？", "预计数量", "装箱数量"]


def _valid_row(prep="贴标"):
    return ["TEST_A", "测试物品", "B0TEST0001", "X00TESTA", "NewItem", prep, "空", "由卖家提供", 10, 10]


def test_dropdown_list_contains_measured_values():
    data = json.loads(DROPDOWN.read_text(encoding="utf-8"))
    blob = json.dumps(data, ensure_ascii=False)
    for value in ("贴标", "空", "由卖家提供"):
        assert value in blob
    loaded = load_sta_dropdowns()
    assert "贴标" in loaded["columns"]["预处理类型"]


def test_prep_xx_is_one_highlight_and_valid_sheet_is_clean():
    bad = precheck_sta_rows([_header(), _valid_row("xx")])
    assert len(bad) == 1
    assert bad[0]["column"] == "预处理类型"

    good = precheck_sta_rows([_header(), _valid_row("贴标"), _valid_row("空")])
    assert good == []


def test_batch13_equivalent_sta_file_has_no_highlight():
    """合成的实际上传成功等价表：实测下拉取值，预检 0 条。真实第13批文件不进仓库。"""
    wb = Workbook()
    ws = wb.active
    ws.append(["请在下方提供此装箱组的包装箱详情。"])
    ws.append(_header())
    ws.append(_valid_row("贴标"))
    ws.append(["TEST_B", "测试物品乙", "B0TEST0002", "X00TESTB", "新品", "空", "由卖家提供", "由亚马逊提供", 4, 4])
    bio = io.BytesIO()
    wb.save(bio)
    from fba_tool.sta_precheck import precheck_sta_bytes

    assert precheck_sta_bytes(bio.getvalue()) == []


def test_step3_zip_has_four_fixed_names():
    body = {
        "confirm_weight_warnings": True,
        "rows": [
            {
                "SKU简称": "TEST_A",
                "FNSKU": "X00TESTA",
                "发货总数": 4,
                "单箱装量": 4,
                "箱长(cm)": 40,
                "箱宽(cm)": 30,
                "箱高(cm)": 20,
                "单个重量(kg)": 1,
                "空纸箱重(kg)": 0.2,
                "单箱毛重(kg)": 4.2,
            }
        ],
        "box_editor": [{"箱号": 1, "来源": "整箱", "SKU简称": "TEST_A", "数量": 4}],
    }
    res = TestClient(app).post("/api/export/step3/bundle", json=body)
    assert res.status_code == 200, res.text
    with zipfile.ZipFile(io.BytesIO(res.content)) as archive:
        assert archive.namelist() == ["STA.xlsx", "内部表.xlsx", "装箱单.xlsx", "实操单.xlsx"]


def test_warehouse_conflict_keeps_csv():
    class Page:
        def __init__(self, code):
            self.warehouse_code = code

    conflict = warehouse_conflict("CLT2", [Page("LAS1"), Page("LAS1")])
    assert conflict["csv_code"] == "CLT2"
    assert conflict["pdf_code"] == "LAS1"
    assert "已采用 CSV" in conflict["message"]
    assert warehouse_conflict("CLT2", [Page("CLT2")]) is None


def test_click_budget_is_half_the_baseline():
    import importlib.util

    path = ROOT / "scripts" / "e2e" / "click_count.py"
    spec = importlib.util.spec_from_file_location("click_count", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    module.check()


def test_missing_unit_dims_say_package_size():
    result = PlacementFeeEngine().compute_shipment(
        [
            {"SKU简称": "TEST_A", "发货总数": 4},
            {"SKU简称": "TEST_B", "发货总数": 2},
        ]
    )
    reasons = [row["ineligible_reason"] for row in result["line_items"]]
    assert reasons == ["单品包装尺寸缺失", "单品包装尺寸缺失"]
    assert "外箱尺寸缺失" not in "".join(reasons)
