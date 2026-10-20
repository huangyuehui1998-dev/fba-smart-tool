"""S1c 文本录入解析：按表头识别列、FNSKU 列、Tab/逗号/空格分隔、解析失败报错（方案 3.1）。"""
import pandas as pd
import pytest

from fba_tool.data_processing import parse_smart_text, parse_smart_text_detailed


def _one(text):
    df, errors, warnings = parse_smart_text_detailed(text)
    assert errors == [], errors
    assert len(df) == 1
    return df.iloc[0], warnings


def test_legacy_positional_comma_still_works():
    row, _ = _one("HUI-2PCS,120,24,60,40,35,0.8,0.5")
    assert row["SKU简称"] == "HUI-2PCS"
    assert row["发货总数"] == 120 and row["单箱装量"] == 24
    assert (row["箱长(cm)"], row["箱宽(cm)"], row["箱高(cm)"]) == (60, 40, 35)
    assert row["单个重量(kg)"] == 0.8 and row["空纸箱重(kg)"] == 0.5
    assert row["单箱毛重(kg)"] is None or pd.isna(row["单箱毛重(kg)"])


def test_header_tab_with_fnsku_in_any_order_and_empty_cell():
    text = (
        "FNSKU\tSKU简称*\t发货总数*\t单箱装量*\t箱长(cm)*\t箱宽(cm)*\t箱高(cm)*\t单个重量(kg)\t空纸箱重(kg)\t单箱毛重(kg)\n"
        "X0059EFBRF\tPM-80\t52\t4\t44.96\t44.96\t40.89\t1.6\t0.5\t7.5\n"
        "\tPM-100\t32\t4\t44.96\t44.96\t40.89\t2.1\t0.5\t\n"
    )
    df, errors, _ = parse_smart_text_detailed(text)
    assert errors == []
    assert list(df["SKU简称"]) == ["PM-80", "PM-100"]
    assert list(df["FNSKU"]) == ["X0059EFBRF", ""]
    assert df.iloc[0]["单箱毛重(kg)"] == 7.5
    assert df.iloc[1]["箱长(cm)"] == 44.96  # 空 FNSKU 单元格不会让后面的列错位


def test_header_reordered_columns():
    text = "发货总数,SKU简称,箱高,箱宽,箱长,单箱装量\n100,ABC,30,40,50,10"
    row, _ = _one(text)
    assert row["SKU简称"] == "ABC" and row["发货总数"] == 100 and row["单箱装量"] == 10
    assert (row["箱长(cm)"], row["箱宽(cm)"], row["箱高(cm)"]) == (50, 40, 30)


def test_headerless_with_fnsku_second_column_space_separated():
    row, _ = _one("PM-80   X0059EFBRF  52 4 44.96 44.96 40.89 1.6 0.5 7.5")
    assert row["SKU简称"] == "PM-80" and row["FNSKU"] == "X0059EFBRF"
    assert row["发货总数"] == 52 and row["单箱装量"] == 4
    assert row["单箱毛重(kg)"] == 7.5


def test_bom_and_fullwidth_and_thousands():
    text = "\ufeffSKU简称\t发货总数\t单箱装量\t箱长\t箱宽\t箱高\nA\t1,000\t２０\t６０\t40\t35"
    row, _ = _one(text)
    assert row["发货总数"] == 1000 and row["单箱装量"] == 20 and row["箱长(cm)"] == 60


def test_unit_suffix_extracted_with_warning():
    row, warnings = _one("A,120,24箱,60,40,35")
    assert row["单箱装量"] == 24
    assert warnings and warnings[0]["field"] == "单箱装量" and warnings[0]["value"] == "24箱"


@pytest.mark.parametrize(
    "text,field,value",
    [
        ("A,abc,24,60,40,35", "发货总数", "abc"),
        ("A,120,0,60,40,35", "单箱装量", "0"),
        ("A,120,24,-60,40,35", "箱长(cm)", "-60"),
        ("A,120,24,60,40,35,x.y", "单个重量(kg)", "x.y"),
        ("A,12.5,24,60,40,35", "发货总数", "12.5"),
    ],
)
def test_bad_values_report_error_not_zero(text, field, value):
    df, errors, _ = parse_smart_text_detailed(text)
    assert len(df) == 0
    assert len(errors) == 1
    e = errors[0]
    assert set(e) == {"row", "field", "value", "message"}
    assert e["row"] == 1 and e["field"] == field and e["value"] == value
    assert field in e["message"]


def test_too_few_columns_is_error():
    # S2 起箱规可留空，最少只要 SKU简称、发货总数 两列；只有 1 列仍报错
    df, errors, _ = parse_smart_text_detailed("A")
    assert len(df) == 0 and errors[0]["row"] == 1 and "列" in errors[0]["message"]


def test_header_missing_required_column_is_error():
    # S2 起表头只强制 SKU简称、发货总数；缺发货总数仍报错
    df, errors, _ = parse_smart_text_detailed("SKU简称,单箱装量\nA,10")
    assert len(df) == 0 and any("发货总数" in e["message"] for e in errors)


def test_row_numbers_count_input_lines():
    text = "SKU简称,发货总数,单箱装量,箱长,箱宽,箱高\n\nA,10,5,60,40,35\nB,bad,5,60,40,35"
    df, errors, _ = parse_smart_text_detailed(text)
    assert list(df["SKU简称"]) == ["A"]
    assert errors[0]["row"] == 4


def test_parse_smart_text_backward_compatible_dataframe():
    df = parse_smart_text("A,10,5,60,40,35\nB,bad,5,60,40,35")
    assert isinstance(df, pd.DataFrame)
    assert list(df["SKU简称"]) == ["A"]  # 坏行不再以 0 混进结果


def test_api_parse_text_reports_errors():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    ok = client.post("/api/parse_text", json={"text": "A,10,5,60,40,35"})
    assert ok.status_code == 200 and ok.json()["count"] == 1
    bad = client.post("/api/parse_text", json={"text": "A,abc,5,60,40,35"})
    assert bad.status_code == 422
    detail = bad.json()["detail"]
    assert "发货总数" in detail["message"]
    assert detail["errors"][0] == {"row": 1, "field": "发货总数", "value": "abc", "message": detail["errors"][0]["message"]}


def test_thousands_separator_with_comma_delimiter_hint():
    from fba_tool.data_processing import parse_smart_text_detailed

    df, errors, warnings = parse_smart_text_detailed("SKU-A,1,000,20,50,40,30")
    msgs = " ".join(e["message"] for e in errors + warnings)
    assert "千分位" in msgs and "Tab" in msgs
    # 列数刚好对上、值也合法时（1,500 被拆成 1 和 500）也要给提示
    df, errors, warnings = parse_smart_text_detailed("SKU-A,1,500,50,40,30")
    assert any("千分位" in w["message"] for w in warnings + errors)
    # 正常逗号行不提示
    df, errors, warnings = parse_smart_text_detailed("SKU-A,100,20,50,40,30")
    assert not any("千分位" in w["message"] for w in warnings + errors)


def test_s2_blank_carton_fields_warn_and_leave_for_master():
    """S2：粘贴录入与 Excel 同规则——单箱装量、箱规留空只提示，由产品库补齐。"""
    from fba_tool.data_processing import parse_smart_text_detailed

    for raw in ("SKU-A\t100\t\t\t\t", "SKU-A,100", "SKU简称\t发货总数\nSKU-A\t100"):
        df, errors, warnings = parse_smart_text_detailed(raw)
        assert errors == [], (raw, errors)
        assert len(df) == 1 and int(df.iloc[0]["发货总数"]) == 100
        assert {"单箱装量", "箱长(cm)", "箱宽(cm)", "箱高(cm)"} <= {w["field"] for w in warnings}


def test_s2_partial_carton_dims_is_error_both_paths():
    import io as _io

    import openpyxl as _ox

    from fba_tool.data_processing import load_from_excel_detailed, parse_smart_text_detailed

    _df, errors, _w = parse_smart_text_detailed("SKU-A,100,20,50")
    assert any(e["field"] == "箱规" for e in errors)
    wb = _ox.Workbook(); ws = wb.active
    ws.append(["SKU简称*", "FNSKU", "发货总数*", "单箱装量*", "箱长(cm)*", "箱宽(cm)*", "箱高(cm)*"])
    ws.append(["A", "", 100, 20, 50, None, None])
    b = _io.BytesIO(); wb.save(b)
    _df, _fn, errors, _w = load_from_excel_detailed(b.getvalue())
    assert any(e["field"] == "箱规" for e in errors)


def test_s2_missing_total_qty_still_error():
    from fba_tool.data_processing import parse_smart_text_detailed

    _df, errors, _w = parse_smart_text_detailed("SKU-A\t\t20\t50\t40\t30")
    assert any(e["field"] == "发货总数" for e in errors)
