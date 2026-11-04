"""v4.2.0 Comprehensive Verification Suite (TC-01 through TC-16).

Verifies official Amazon policy compliance, routing warehouse resolution,
box count robustness, edge cases, and mutant kill guarantees.
"""
import pytest
import pandas as pd
from decimal import Decimal

from fba_tool.models import SkuRow
from fba_tool.fba_compliance import (
    evaluate_fba_boxing_compliance,
    check_box_count_limit,
    _scan_boxes,
    _calc_box_count,
    dimension_blocked,
    classify_box_weight,
)
from fba_tool.routing_service import (
    resolve_routing_warehouse,
    strict_warehouse_from_filename,
    sanitize_filename,
    extract_ticket_rank,
)


def _make_sku(sku="SKU-A", qty=1, per_box=1, l=70.0, w=40.0, h=30.0, unit_kg=10.0,
              u_l=0.0, u_w=0.0, u_h=0.0, u_kg=0.0):
    return SkuRow(
        sku=sku,
        total_qty=qty,
        carton_qty=per_box,
        length_cm=l,
        width_cm=w,
        height_cm=h,
        unit_weight_kg=unit_kg,
        carton_tare_kg=0.5,
        unit_length_cm=u_l,
        unit_width_cm=u_w,
        unit_height_cm=u_h,
    )


# TC-01: 单箱 1 件单品，长 70cm (27.5 in)，FBA 放行
def test_tc01_single_oversize_fba_allowed():
    sku = _make_sku(qty=1, per_box=1, l=70.0, w=40.0, h=30.0, u_l=68.0, u_w=38.0, u_h=28.0)
    editor = pd.DataFrame([{"箱号": 1, "SKU简称": "SKU-A", "数量": 1}])
    metrics = pd.DataFrame([{"箱号": 1, "毛重(kg)": 15.0}])
    comp = evaluate_fba_boxing_compliance(editor, [sku], metrics, destination="FBA")
    assert comp["blocked"] is False
    assert comp["side_violation_count"] == 0


# TC-02: 单箱 1 件单品，长 70cm，AWD 硬阻断
def test_tc02_single_oversize_awd_blocked():
    sku = _make_sku(qty=1, per_box=1, l=70.0, w=40.0, h=30.0, u_l=68.0, u_w=38.0, u_h=28.0)
    editor = pd.DataFrame([{"箱号": 1, "SKU简称": "SKU-A", "数量": 1}])
    metrics = pd.DataFrame([{"箱号": 1, "毛重(kg)": 15.0}])
    comp = evaluate_fba_boxing_compliance(editor, [sku], metrics, destination="AWD")
    assert comp["blocked"] is True
    assert comp["side_violation_count"] >= 1
    assert any("AWD" in line for line in comp["summary_lines"])


# TC-03: 混装箱 2 件商品，长 70cm，FBA 硬阻断
def test_tc03_multi_item_oversize_fba_blocked():
    sku = _make_sku(qty=2, per_box=2, l=70.0, w=40.0, h=30.0, u_l=30.0, u_w=20.0, u_h=15.0)
    editor = pd.DataFrame([{"箱号": 1, "SKU简称": "SKU-A", "数量": 2}])
    metrics = pd.DataFrame([{"箱号": 1, "毛重(kg)": 15.0}])
    comp = evaluate_fba_boxing_compliance(editor, [sku], metrics, destination="FBA")
    assert comp["blocked"] is True
    assert comp["side_violation_count"] >= 1


# TC-04: 单品缺净尺寸，单箱 1 件，长 70cm，柔性放行 (Soft Warn)
def test_tc04_missing_unit_dimensions_soft_warn():
    sku = _make_sku(qty=1, per_box=1, l=70.0, w=40.0, h=30.0, u_l=0.0, u_w=0.0, u_h=0.0)
    editor = pd.DataFrame([{"箱号": 1, "SKU简称": "SKU-A", "数量": 1}])
    metrics = pd.DataFrame([{"箱号": 1, "毛重(kg)": 15.0}])
    comp = evaluate_fba_boxing_compliance(editor, [sku], metrics, destination="FBA")
    assert comp["blocked"] is False


# TC-05: 单箱单件毛重 24.5 kg (54 lb)，放行，提示 5 面 Team Lift
def test_tc05_single_oversize_team_lift_5_labels():
    sku = _make_sku(qty=1, per_box=1, l=70.0, w=40.0, h=30.0, unit_kg=24.0, u_l=68.0, u_w=38.0, u_h=28.0)
    editor = pd.DataFrame([{"箱号": 1, "SKU简称": "SKU-A", "数量": 1}])
    metrics = pd.DataFrame([{"箱号": 1, "毛重(kg)": 24.5}])
    comp = evaluate_fba_boxing_compliance(editor, [sku], metrics, destination="FBA")
    assert comp["blocked"] is False
    assert len(comp["lift_notices"]) == 1
    notice = comp["lift_notices"][0]
    assert notice["label"] == "Team Lift"
    assert "共贴 5 张 Team Lift 标签" in notice["message"]


# TC-06: 刷仓模式下 第二票ONT8.csv，CSV 为 GYR3，文件名 ONT8 胜出
def test_tc06_routing_mode_filename_wins():
    wh, src, warn = resolve_routing_warehouse("GYR3", "第二票ONT8.csv", is_routing_mode=True)
    assert wh == "ONT8"
    assert src == "文件名"
    assert warn is not None
    assert "GYR3" in warn and "ONT8" in warn


# TC-07: batch_box1.csv，CSV 内容为 ONT8，BOX1 黑名单拦截，回退 ONT8
def test_tc07_blacklist_token_box1():
    wh, src, warn = resolve_routing_warehouse("ONT8", "batch_box1.csv", is_routing_mode=True)
    assert wh == "ONT8"
    assert src == "CSV"


# TC-08: 路径穿越 ../../hack_ONT8.csv 安全剥离
def test_tc08_path_traversal_sanitized():
    sanitized = sanitize_filename("../../hack_ONT8.csv")
    assert sanitized == "hack_ONT8.csv"
    sanitized_win = sanitize_filename(r"..\..\hack_ONT8.csv")
    assert sanitized_win == "hack_ONT8.csv"
    null_byte = sanitize_filename("test\x00ONT8.csv")
    assert "\x00" not in null_byte


# TC-09: 箱号 [1, 2, 205]（共 3 箱），箱数统计为 3，不误报超 200 箱
def test_tc09_discrete_box_numbers():
    df = pd.DataFrame({"箱号": [1, 2, 205], "数量": [10, 10, 10]})
    count = _calc_box_count(df)
    assert count == 3
    warn = check_box_count_limit(df)
    assert warn is None


# TC-10: 回归现有 test_s8_fix 契约：is_routing_mode=False 时 CSV 优先
def test_tc10_legacy_routing_mode_csv_wins():
    wh, src, warn = resolve_routing_warehouse("SMF3", "第一票ONT8.csv", is_routing_mode=False)
    assert (wh, src) == ("SMF3", "CSV")
    assert warn is not None and "ONT8" in warn


# TC-11: 63.50000 vs 63.50001 Decimal 极值精度断言
def test_tc11_decimal_boundary_precision():
    # 63.5 cm = 25.0 in exactly
    assert dimension_blocked(63.50000, 50.0, 40.0) is False
    assert dimension_blocked(63.50001, 50.0, 40.0) is True


# TC-12: 50 lb / 100 lb 毛重临界点四阶断言
def test_tc12_gross_weight_tiers():
    # 标准混装箱阶梯
    assert classify_box_weight(22.0) == "ok"
    assert classify_box_weight(22.6) == "warn"  # 内部预警阈值 22.5kg
    assert classify_box_weight(22.6801) == "block"  # > 50 lb 混装硬阻断
    # 单件大件箱阶梯 (single_oversize=True)
    assert classify_box_weight(22.6801, single_oversize=True) == "team_lift"  # > 50 lb
    assert classify_box_weight(45.3592, single_oversize=True) == "team_lift"  # <= 100 lb
    assert classify_box_weight(45.3601, single_oversize=True) == "mechanical_lift"  # > 100 lb


# TC-13: 多行装箱数据杀伤 count() 变异体
def test_tc13_multi_row_kills_count_mutant():
    # 7 行数据，但只有 3 个箱号 (1, 1, 1, 2, 2, 3, 3)
    df = pd.DataFrame({"箱号": [1, 1, 1, 2, 2, 3, 3], "SKU简称": ["A"] * 7, "数量": [5] * 7})
    assert _calc_box_count(df) == 3


# TC-14: 极端文件名与白名单负向拦截测试
def test_tc14_unknown_warehouse_filename():
    assert strict_warehouse_from_filename("第一票_BOX1.csv") == ""
    assert strict_warehouse_from_filename("CON.csv") == ""
    assert extract_ticket_rank("第三票ONT8.csv") == 3


# TC-15: 缓冲物超标预警 (>2 in) 断言
def test_tc15_cushion_slack_warning():
    # 外箱 75cm (29.5 in)，单品 65cm (25.6 in) -> 差值 10cm (3.94 in > 2.0 in)
    sku = _make_sku(qty=1, per_box=1, l=75.0, w=40.0, h=30.0, u_l=65.0, u_w=38.0, u_h=28.0)
    editor = pd.DataFrame([{"箱号": 1, "SKU简称": "SKU-A", "数量": 1}])
    metrics = pd.DataFrame([{"箱号": 1, "毛重(kg)": 15.0}])
    comp = evaluate_fba_boxing_compliance(editor, [sku], metrics, destination="FBA")
    assert comp["blocked"] is False
    assert len(comp["box_fit_warnings"]) >= 1
    assert "缓冲衬垫厚度 ≤ 2 英寸" in comp["box_fit_warnings"][0]["message"]


# TC-16: 纯字符串箱号安全回退
def test_tc16_string_box_ids():
    df = pd.DataFrame({"箱号": ["BOX-A", "BOX-B", "BOX-C"], "数量": [10, 10, 10]})
    assert _calc_box_count(df) == 3

# TC-17: AWD 仓库单箱毛重 24.0 kg (> 50 lb / 22.68 kg) 硬阻断
def test_tc17_awd_gross_weight_blocked():
    sku = _make_sku(qty=1, per_box=1, l=50.0, w=40.0, h=30.0, unit_kg=24.0, u_l=48.0, u_w=38.0, u_h=28.0)
    editor = pd.DataFrame([{"箱号": 1, "SKU简称": "SKU-A", "数量": 1}])
    metrics = pd.DataFrame([{"箱号": 1, "毛重(kg)": 24.0}])
    comp = evaluate_fba_boxing_compliance(editor, [sku], metrics, destination="AWD")
    assert comp["blocked"] is True
    assert comp["gross_violation_count"] >= 1
    assert any("AWD 仓库上限 50 lb" in v["message"] for v in comp["box_gross_violations"])


# TC-18: 文件名含空字节安全剥离
def test_tc18_null_byte_filename_safety():
    cleaned = sanitize_filename("test\x00ONT8.csv")
    assert "\x00" not in cleaned
    assert "ONT8" in cleaned
    wh = strict_warehouse_from_filename("第一票\x00ONT8.csv")
    assert wh == "ONT8"


# TC-19: 批量上传 DoS 熔断（超过 50 个文件返回 400）
def test_tc19_batch_upload_file_count_limit():
    from fastapi import HTTPException
    from routers.routing import api_routing_preview
    import pytest
    import asyncio

    dummy_files = [object()] * 51
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api_routing_preview(dummy_files))
    assert exc.value.status_code == 400
    assert "50" in str(exc.value.detail)


# TC-20: Excel 公式注入转义测试 (CWE-1236)
def test_tc20_excel_formula_injection_defense():
    from openpyxl import Workbook
    from fba_tool.template_layout import safe_write

    wb = Workbook()
    ws = wb.active
    safe_write(ws, 1, 1, "=cmd|'/c calc'!A0")
    safe_write(ws, 2, 1, "@SUM(1+1)")
    safe_write(ws, 3, 1, "-123.45")  # 正常负数不转义
    safe_write(ws, 4, 1, "-calc")    # 负号加非数字转义

    assert ws.cell(1, 1).value == "'=cmd|'/c calc'!A0"
    assert ws.cell(2, 1).value == "'@SUM(1+1)"
    assert ws.cell(3, 1).value == "-123.45"
    assert ws.cell(4, 1).value == "'-calc"
