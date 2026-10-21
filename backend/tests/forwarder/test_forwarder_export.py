"""货代表导出与预览列一致（无模板）。"""
from io import BytesIO

import pandas as pd
from openpyxl import load_workbook

from fba_tool.excel_export import export_forwarder_quote
from fba_tool.forwarder_quote import FORWARDER_COLUMNS, append_warehouse_subtotals


def test_forwarder_export_matches_preview_columns():
    df = pd.DataFrame(
        [
            {
                "仓库代码": "FWA4",
                "SKU": "SKU-A",
                "箱序号": "1,2",
                "单件实重(kg)": 5.123,
                "箱数": 2,
                "箱子长(cm)": 40.0,
                "箱子宽(cm)": 30.0,
                "箱子高(cm)": 30.0,
                "实重(kg)": 10.25,
                "单箱体积重(kg)": 9.2,
                "总体积重(kg)": 18.4,
            }
        ]
    )
    data = export_forwarder_quote(df)
    wb = load_workbook(BytesIO(data))
    ws = wb.active
    headers = [ws.cell(1, c).value for c in range(1, len(FORWARDER_COLUMNS) + 1)]
    assert headers == FORWARDER_COLUMNS
    assert ws.cell(2, 1).value == "FWA4"
    assert ws.cell(2, 2).value == "SKU-A"
    assert ws.cell(2, FORWARDER_COLUMNS.index("箱数") + 1).value == 2
    assert ws.cell(2, FORWARDER_COLUMNS.index("单件实重(kg)") + 1).value == 5.123
    assert ws.cell(3, 1).value == "FWA4 小计"
    assert "方数:" in str(ws.cell(3, FORWARDER_COLUMNS.index("箱子长(cm)") + 1).value)


def test_forwarder_export_idempotent_with_subtotals():
    base = pd.DataFrame(
        [
            {
                "仓库代码": "GYR2",
                "SKU": "SKU-B",
                "箱序号": "1",
                "单件实重(kg)": 1.0,
                "箱数": 1,
                "箱子长(cm)": 10.0,
                "箱子宽(cm)": 10.0,
                "箱子高(cm)": 10.0,
                "实重(kg)": 1.0,
                "单箱体积重(kg)": 0.2,
                "总体积重(kg)": 0.2,
            }
        ]
    )
    with_sub = append_warehouse_subtotals(base)
    a = export_forwarder_quote(base)
    b = export_forwarder_quote(with_sub)
    # S8 P3（S7 待办 C）：逐格比较单元格值。以前比 xlsx 字节长度，跨秒时 docProps/core.xml 时间戳不同会偶发失败。
    assert _cells(a) == _cells(b)


def _cells(data: bytes):
    wb = load_workbook(BytesIO(data))
    return {ws.title: [[c.value for c in row] for row in ws.iter_rows()] for ws in wb.worksheets}
