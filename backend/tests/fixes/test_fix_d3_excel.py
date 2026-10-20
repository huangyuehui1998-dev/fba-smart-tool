"""S1-fix1 D3：Excel 样表导入与文本录入同一口径，非法值按行号报错，不再静默填 0。"""
from __future__ import annotations

import io

import openpyxl
import pytest

from fba_tool.data_processing import load_from_excel, load_from_excel_detailed

HEADER = ["SKU简称*", "FNSKU", "发货总数*", "单箱装量*", "箱长(cm)*", "箱宽(cm)*", "箱高(cm)*", "单个重量(kg)", "空纸箱重(kg)", "单箱毛重(kg)"]


def _xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADER)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_valid_rows_ok():
    df, fn, errors, warnings = load_from_excel_detailed(_xlsx([["A", "X000000001", 100, 20, 50, 40, 30, 1.2, 0.5, None]]))
    assert errors == []
    assert int(df.iloc[0]["发货总数"]) == 100 and fn == {"A": "X000000001"}


def test_abc_and_negative_reported_with_row_numbers():
    data = _xlsx([
        ["A", "", "abc", 20, 50, 40, 30, 1, 0.5, None],
        ["B", "", 100, -5, 50, 40, 30, 1, 0.5, None],
        ["C", "", 100, 20, 50, 40, 30, 1, 0.5, None],
    ])
    df, _fn, errors, _w = load_from_excel_detailed(data)
    got = {(e["row"], e["field"]) for e in errors}
    assert (2, "发货总数") in got
    assert (3, "单箱装量") in got
    assert list(df["SKU简称"]) == ["C"]


def test_missing_required_and_non_integer():
    data = _xlsx([["A", "", None, 2.5, 50, 40, 30, 1, 0.5, None]])
    _df, _fn, errors, _w = load_from_excel_detailed(data)
    fields = {e["field"] for e in errors}
    assert {"发货总数", "单箱装量"} <= fields


def test_blank_carton_fields_left_for_master_fill():
    """箱规/单箱装量留空 → 提示由产品库补齐，不报错（第3批真实样表就是这样）。"""
    df, _fn, errors, warnings = load_from_excel_detailed(_xlsx([["A", "", 150, None, None, None, None, None, None, None]]))
    assert errors == []
    assert len(df) == 1
    assert {w["field"] for w in warnings} == {"单箱装量", "箱长(cm)", "箱宽(cm)", "箱高(cm)"}


def test_negative_optional_weight_rejected():
    _df, _fn, errors, _w = load_from_excel_detailed(_xlsx([["A", "", 10, 5, 50, 40, 30, -1, 0.5, None]]))
    assert errors and errors[0]["field"] == "单个重量(kg)"


def test_legacy_api_raises_instead_of_zero():
    with pytest.raises(ValueError, match="第2行"):
        load_from_excel(_xlsx([["A", "", "abc", 20, 50, 40, 30, 1, 0.5, None]]))


def test_api_returns_422_with_errors():
    from fastapi.testclient import TestClient
    from main import app

    c = TestClient(app)
    r = c.post("/api/parse_excel", files={"file": ("t.xlsx", _xlsx([["A", "", "abc", 20, 50, 40, 30, 1, 0.5, None]]),
                                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 422
    assert r.json()["detail"]["errors"][0]["row"] == 2
