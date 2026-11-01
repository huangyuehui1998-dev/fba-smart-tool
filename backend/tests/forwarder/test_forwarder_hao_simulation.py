"""真人模拟测试 2：跨境货代排单与刷仓调度专员 - 阿豪 (Hao)

全方位验证货代刷仓、分仓排单、体积小计、货代表导出及零破坏向后兼容。
"""
from __future__ import annotations

import io
import json
import sys
import urllib.parse
from pathlib import Path

# 确保 backend 根目录在 sys.path 中
backend_dir = Path(__file__).resolve().parents[2]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import openpyxl
import pytest
from fastapi.testclient import TestClient

from main import app
from fba_tool.routing_service import (
    strict_warehouse_from_filename,
    resolve_routing_warehouse,
)

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic" / "rebox" / "unassigned_send_min.csv"


def _build_test_csv_bytes(internal_warehouse: str = "ONT8") -> bytes:
    """生成内部货件名称携带旧仓库代码的真实 CSV 字节流"""
    text = FIXTURE_PATH.read_text(encoding="utf-8-sig")
    modified = text.replace('"PLAIN"', f'"FBA-SHIPMENT-{internal_warehouse}"')
    return modified.encode("utf-8-sig")


@pytest.fixture
def client():
    return TestClient(app)


def test_scenario_a_multi_ticket_brushing_filename_wins(client):
    """场景 A：批量上传 3 票刷仓 CSV，内部全为旧仓 ONT8，刷仓模式下 100% 文件名胜出。"""
    csv_bytes = _build_test_csv_bytes("ONT8")
    files = [
        ("files", ("20261101-GYR3-第1票.csv", csv_bytes, "text/csv")),
        ("files", ("20261101-ONT8-第2票.csv", csv_bytes, "text/csv")),
        ("files", ("20261101-SMF3-第3票.csv", csv_bytes, "text/csv")),
    ]
    res = client.post("/api/routing/preview", files=files)
    assert res.status_code == 200, f"预览接口返回错误: {res.text}"

    data = res.json()
    assert len(data) > 0, "预览数据为空"

    # 提取识别出的目标仓库列表（按票序排序）
    wh_list = [r["仓库代码"] for r in data if r.get("仓库代码") and not str(r.get("仓库代码")).endswith("小计")]
    distinct_whs = []
    for w in wh_list:
        if w not in distinct_whs:
            distinct_whs.append(w)

    assert distinct_whs == ["GYR3", "ONT8", "SMF3"], f"仓库识别顺序或代码不符: {distinct_whs}"

    # 验证响应 Header 中的覆盖告警
    warn_raw = res.headers.get("x-routing-warnings")
    assert warn_raw is not None, "缺少 x-routing-warnings 响应头"
    warnings = json.loads(urllib.parse.unquote(warn_raw))
    assert len(warnings) == 2, f"告警数量预期为 2 (GYR3 与 SMF3)，实际为: {warnings}"
    assert any("GYR3" in w and "ONT8" in w for w in warnings)
    assert any("SMF3" in w and "ONT8" in w for w in warnings)


def test_scenario_b_blacklist_token_filtering():
    """场景 B：黑名单 Token 过滤测试，严禁误将 BOX1、CASE1、SKU2 当成仓库代码。"""
    # 1. batch_box1.csv 绝不能提取出 BOX1
    wh_box1 = strict_warehouse_from_filename("batch_box1.csv")
    assert wh_box1 == "", f"误识别黑名单单词 BOX1: {wh_box1}"

    wh, src, warn = resolve_routing_warehouse("ONT8", "batch_box1.csv", is_routing_mode=True)
    assert wh == "ONT8", f"未回退至 CSV 仓库: {wh}"
    assert src == "CSV"

    # 2. case1_ONT8.csv 必须提取 ONT8，排除 CASE1
    wh_case1 = strict_warehouse_from_filename("case1_ONT8.csv")
    assert wh_case1 == "ONT8", f"未能正确识别 ONT8: {wh_case1}"

    wh2, src2, _ = resolve_routing_warehouse("GYR3", "case1_ONT8.csv", is_routing_mode=True)
    assert wh2 == "ONT8"
    assert src2 == "文件名"


def test_scenario_c_warehouse_subtotals_cbm_and_weights(client):
    """场景 C：各仓库分票汇总，验证箱数、重量及体积 CBM 小计准确无误。"""
    csv_bytes = _build_test_csv_bytes("ONT8")
    files = [
        ("files", ("20261101-GYR3-第1票.csv", csv_bytes, "text/csv")),
        ("files", ("20261101-ONT8-第2票.csv", csv_bytes, "text/csv")),
        ("files", ("20261101-SMF3-第3票.csv", csv_bytes, "text/csv")),
    ]
    res = client.post("/api/routing/preview", files=files)
    assert res.status_code == 200
    rows = res.json()

    subtotal_rows = [r for r in rows if "小计" in str(r.get("仓库代码", ""))]
    assert len(subtotal_rows) == 3, f"小计行数不等于 3: {len(subtotal_rows)}"

    for s_row in subtotal_rows:
        wh_name = str(s_row.get("仓库代码", ""))
        boxes = s_row.get("箱数")
        assert boxes == 32, f"{wh_name} 箱数不匹配，预期 32 箱，实际 {boxes}"

        total_units = s_row.get("发货总数", s_row.get("总件数"))
        assert total_units == 128, f"{wh_name} 件数不匹配，预期 128 件，实际 {total_units}"

        total_weight = float(s_row.get("总体积重(kg)", s_row.get("总重(kg)", 0)))
        assert abs(total_weight - 222.864) < 0.01, f"{wh_name} 体积重不匹配: {total_weight}"

        total_actual_weight = float(s_row.get("总实重(kg)", 0))
        assert abs(total_actual_weight - 145.28) < 0.01, f"{wh_name} 实重不匹配: {total_actual_weight}"

        cbm_val = s_row.get("_subtotal_cbm")
        assert cbm_val == 1.337, f"{wh_name} 数值 CBM 不匹配: {cbm_val}"
        cbm_str = str(s_row.get("箱子长(cm)", s_row.get("外箱长(cm)", "")))
        assert "1.337 CBM" in cbm_str, f"{wh_name} 体积小计文本不匹配: {cbm_str}"


def test_scenario_d_excel_export_forwarder_table(client):
    """场景 D：导出《刷仓货代表.xlsx》，解析二进制验证表头、小计样式与数据完整性。"""
    csv_bytes = _build_test_csv_bytes("ONT8")
    files = [
        ("files", ("20261101-GYR3-第1票.csv", csv_bytes, "text/csv")),
        ("files", ("20261101-ONT8-第2票.csv", csv_bytes, "text/csv")),
        ("files", ("20261101-SMF3-第3票.csv", csv_bytes, "text/csv")),
    ]
    preview_res = client.post("/api/routing/preview", files=files)
    preview_data = preview_res.json()

    # 导出测试
    export_res = client.post("/api/routing/export", json={"forwarder": preview_data})
    assert export_res.status_code == 200
    assert "spreadsheetml.sheet" in export_res.headers.get("content-type", "")

    content = export_res.content
    assert len(content) > 1000, "导出的 Excel 文件损坏或体积过小"

    wb = openpyxl.load_workbook(io.BytesIO(content))
    ws = wb.active

    # 验证行数：1 行表头 + 3 仓 * (2 行明细 + 1 行小计) = 10 行
    assert ws.max_row == 10, f"表格总行数不匹配，预期 10 行，实际 {ws.max_row}"
    assert ws.max_column >= 13, f"表格列数不足: {ws.max_column}"

    # 验证表头
    headers = [ws.cell(row=1, column=c).value for c in range(1, 6)]
    assert headers[:4] == ["仓库代码", "SKU", "箱序号", "箱数"]

    # 验证小计行（第 4、7、10 行）
    for row_idx in (4, 7, 10):
        wh_cell = ws.cell(row=row_idx, column=1)
        assert "小计" in str(wh_cell.value)
        assert wh_cell.font.bold is True, f"小计行字体未加粗: 行 {row_idx}"
        fill_rgb = wh_cell.fill.start_color.rgb
        assert fill_rgb == "00EFF6FF", f"小计行底色未渲染为浅蓝 (00EFF6FF): {fill_rgb}"

        cbm_cell = ws.cell(row=row_idx, column=5)
        assert "1.337 CBM" in str(cbm_cell.value), f"小计行 CBM 未正确填充: {cbm_cell.value}"


def test_scenario_e_backward_compatibility_regular_shipment():
    """场景 E：零破坏向后兼容验证，is_routing_mode=False 时保持 CSV 优先。"""
    # 模拟普通单票发货业务：CSV 内为 SMF3，文件名带有第一票ONT8.csv
    wh, src, warn = resolve_routing_warehouse("SMF3", "第一票ONT8.csv", is_routing_mode=False)
    assert wh == "SMF3", f"常规模式未保持 CSV 优先: {wh}"
    assert src == "CSV"
    assert warn is not None and "按 CSV 用 SMF3" in warn

    # CSV 为空时，常规模式才回退到文件名
    wh2, src2, warn2 = resolve_routing_warehouse("", "第一票ONT8.csv", is_routing_mode=False)
    assert wh2 == "ONT8"
    assert src2 == "文件名"
    assert warn2 is not None and "按文件名用 ONT8" in warn2


if __name__ == "__main__":
    import sys
    print("=" * 60)
    print("【阿豪测试专员】正在执行跨境货代排单与刷仓调度全流程自动化回归...")
    print("=" * 60)
    cli = TestClient(app)
    t0 = pytest.importorskip("time").perf_counter()
    test_scenario_a_multi_ticket_brushing_filename_wins(cli)
    print("[PASS] 场景 A: 批量刷仓 100% 文件名胜出且审计告警完备")
    test_scenario_b_blacklist_token_filtering()
    print("[PASS] 场景 B: 黑名单 Token 过滤严密，杜绝 BOX1/CASE1 误判")
    test_scenario_c_warehouse_subtotals_cbm_and_weights(cli)
    print("[PASS] 场景 C: 各仓库分票汇总 CBM、重量与箱数统计精准")
    test_scenario_d_excel_export_forwarder_table(cli)
    print("[PASS] 场景 D: 《刷仓货代表.xlsx》样式、底色与小计解析验证通过")
    test_scenario_e_backward_compatibility_regular_shipment()
    print("[PASS] 场景 E: 零破坏向后兼容验证通过，常规发货 CSV 优先无缝兼容")
    cost = pytest.importorskip("time").perf_counter() - t0
    print(f"全部 5 大场景自动化测试 100% 通过！总耗时: {cost:.3f} 秒")
    print("=" * 60)
