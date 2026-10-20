"""R12-18：STA 预检停在箱信息标签行。"""
from __future__ import annotations

import logging

from fba_tool.sta_precheck import BOX_LABEL_PREFIXES, precheck_sta_rows


def _header():
    return ["SKU", "商品名称", "ASIN", "FNSKU", "状况", "预处理类型", "商品预处理方是谁？", "商品贴标方是谁？", "预计数量"]


def _sku(sku="TEST_A", fnsku="X00TESTA"):
    return [sku, "测试物品", "B0TEST0001", fnsku, "NewItem", "贴标", "空", "由卖家提供", 4]


def _sheet(n=3):
    rows = [
        ["装箱组"],
        ["仓库"],
        [f"SKU 总数：{n}"],
        [],
        _header(),
    ]
    rows.extend(_sku(f"TEST_{i}") for i in range(n))
    rows.append([])
    rows.extend([
        ["包装箱名称"],
        ["包装箱重量（磅）："],
        ["包装箱宽度（英寸）："],
        ["包装箱长度（英寸）："],
        ["包装箱高度（英寸）："],
    ])
    return rows


def test_label_prefixes_are_a_constant():
    assert BOX_LABEL_PREFIXES == (
        "包装箱名称",
        "包装箱重量",
        "包装箱宽度",
        "包装箱长度",
        "包装箱高度",
        "箱号",
    )


def test_n3_labels_at_rows_10_to_14_are_not_highlighted():
    rows = _sheet(3)
    assert [index + 1 for index, row in enumerate(rows) if row and str(row[0]).startswith("包装箱")] == [10, 11, 12, 13, 14]
    assert precheck_sta_rows(rows) == []


def test_sku_count_mismatch_is_one_yellow_warning():
    rows = _sheet(3)
    rows[2] = ["SKU 总数：9"]
    notes = precheck_sta_rows(rows)
    assert len(notes) == 1
    assert notes[0]["level"] == "yellow"
    assert "截断" in notes[0]["message"]


def test_label_row_and_unknown_sku_are_not_required_errors(caplog):
    rows = [_header(), ["包装箱名称", "", "", "", "", "", "", "", ""]]
    assert precheck_sta_rows(rows) == []
    rows = [
        ["SKU 总数：1"],
        [],
        [],
        [],
        _header(),
        _sku("TEST_A"),
        [],
        ["包装箱名称"],
        _sku("TEST_EXTRA"),
    ]
    with caplog.at_level(logging.DEBUG, logger="fba_tool.sta_precheck"):
        notes = precheck_sta_rows(rows, known_skus=["TEST_A"])
    assert notes == []
    assert "TEST_EXTRA" in caplog.text
    missing = precheck_sta_rows([_header(), ["TEST_A", "测试物品", "B0TEST0001", "", "NewItem", "贴标", "空", "由卖家提供", 4]])
    assert any(item["column"] == "FNSKU" and item["message"] == "必填项为空" for item in missing)
