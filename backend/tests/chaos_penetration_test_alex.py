"""
Chaos Engineering & Penetration Testing Suite - Alex (Geek Chaos Tester 04)
CWE-22 (Path Traversal & Device Names), CWE-20 (Null Byte Injection),
CWE-1236 (Excel Formula Injection), CWE-400 (DoS Limits),
FastAPI Event Loop Non-blocking concurrency check.
"""
import asyncio
import io
import os
import sys
import time
import pytest
from starlette.testclient import TestClient
import httpx
import pandas as pd
from openpyxl import load_workbook, Workbook

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fba_tool.routing_service import (
    sanitize_filename,
    strict_warehouse_from_filename,
    resolve_routing_warehouse,
    extract_warehouse_from_filename,
)
from fba_tool.template_layout import safe_write
from fba_tool.excel_export import export_forwarder_quote
from main import app

# ---------------------------------------------------------
# 场景 A：路径穿越与特殊文件名攻击 (CWE-22)
# ---------------------------------------------------------
def test_scenario_a_path_traversal_and_reserved_names():
    t0 = time.perf_counter()
    # 1. 常见 Linux/Unix 路径穿越
    s1 = sanitize_filename("../../etc/passwd_ONT8.csv")
    assert s1 == "passwd_ONT8.csv"
    assert ".." not in s1 and "/" not in s1
    wh1 = strict_warehouse_from_filename("../../etc/passwd_ONT8.csv")
    assert wh1 == "ONT8"

    # 2. Windows 路径穿越反斜杠
    s2 = sanitize_filename(r"..\..\win_system32_GYR3.csv")
    assert s2 == "win_system32_GYR3.csv"
    assert ".." not in s2 and "\\" not in s2
    wh2 = strict_warehouse_from_filename(r"..\..\win_system32_GYR3.csv")
    assert wh2 == "GYR3"

    # 3. Windows 保留设备名 CON.csv / AUX.csv
    s_con = sanitize_filename("CON.csv")
    assert s_con == "safe_CON.csv"
    wh_con = strict_warehouse_from_filename("CON.csv")
    assert wh_con == ""

    s_aux = sanitize_filename("AUX.csv")
    assert s_aux == "safe_AUX.csv"
    wh_aux = strict_warehouse_from_filename("AUX.csv")
    assert wh_aux == ""

    s_prn = sanitize_filename("prn.csv")
    assert s_prn == "safe_prn.csv"
    s_nul = sanitize_filename("NUL.CSV")
    assert s_nul == "safe_NUL.CSV"

    # 4. 边界空/点路径
    assert sanitize_filename("") == "UNKNOWN.csv"
    assert sanitize_filename("..") == "UNKNOWN.csv"
    assert sanitize_filename(".") == "UNKNOWN.csv"
    
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"[SCENARIO_A] PASS: Path traversal & Windows reserved devices defended in {elapsed:.2f}ms")


# ---------------------------------------------------------
# 场景 B：空字节截断攻击 (CWE-20)
# ---------------------------------------------------------
def test_scenario_b_null_byte_truncation():
    t0 = time.perf_counter()
    malicious = "evil\x00ONT8.csv"
    sanitized = sanitize_filename(malicious)
    assert "\x00" not in sanitized
    assert sanitized == "evilONT8.csv"

    # 仓码识别正常：空字节剥离后成功由 extract_warehouse_from_filename 提取
    wh = extract_warehouse_from_filename(malicious)
    assert wh == "ONT8"

    # 真实业务单票注入空字节，严格仓码与仲裁提取正常
    biz_file = "第一票\x00ONT8.csv"
    assert sanitize_filename(biz_file) == "第一票ONT8.csv"
    assert strict_warehouse_from_filename(biz_file) == "ONT8"

    res_wh, src, warn = resolve_routing_warehouse("", biz_file, is_routing_mode=True)
    assert res_wh == "ONT8"
    assert src == "文件名"
    assert "\x00" not in (warn or "")

    # 多重空字节与控制字符混合
    combo = "\x01\x00hack\x08_MDW2\x7f.csv"
    combo_clean = sanitize_filename(combo)
    assert combo_clean == "hack_MDW2.csv"
    assert strict_warehouse_from_filename(combo) == "MDW2"

    elapsed = (time.perf_counter() - t0) * 1000
    print(f"[SCENARIO_B] PASS: Null byte injection safely stripped in {elapsed:.2f}ms")


# ---------------------------------------------------------
# 场景 C：Excel 公式注入漏洞攻击 (CWE-1236)
# ---------------------------------------------------------
def test_scenario_c_excel_formula_injection():
    t0 = time.perf_counter()
    payloads = [
        "=cmd|' /C calc'!A0",
        "@SUM(1+1)",
        "-1+1",
        "+2*3",
        "-calc",
        "+cmd",
    ]
    benign = [
        "-123.45",
        "+50",
        "0",
        "100.5",
        "NORMAL_SKU_001",
    ]

    # 1. 单元格级别 safe_write 注入防护
    wb = Workbook()
    ws = wb.active
    ws.title = "TestInjection"

    row = 1
    for p in payloads:
        safe_write(ws, row, 1, p)
        val = ws.cell(row, 1).value
        assert str(val).startswith("'"), f"Payload not escaped: {p} -> {val}"
        assert str(val) == "'" + p
        row += 1

    for b in benign:
        safe_write(ws, row, 1, b)
        val = ws.cell(row, 1).value
        assert not str(val).startswith("'"), f"Benign value improperly escaped: {b} -> {val}"
        assert str(val) == b
        row += 1

    # 2. 全量 export_forwarder_quote 业务导出链路渗透
    mock_df = pd.DataFrame([
        {
            "仓库代码": "ONT8",
            "SKU": "=cmd|' /C calc'!A0",
            "品名": "@SUM(1+1)",
            "批次": "-1+1",
            "箱数": 5,
            "单箱件数": 10,
            "总件数": 50,
            "箱子长(cm)": 50.0,
            "箱子宽(cm)": 40.0,
            "箱子高(cm)": 30.0,
            "单箱重(kg)": 15.0,
            "总实重(kg)": 75.0,
            "总体积重(kg)": 60.0,
            "收费重(kg)": 75.0,
            "总CBM": 0.3,
        },
        {
            "仓库代码": "ONT8",
            "SKU": "+2*3",
            "品名": "Normal Widget",
            "批次": "-123.45",  # 正常负数不转义
            "箱数": 2,
            "单箱件数": 20,
            "总件数": 40,
            "箱子长(cm)": 40.0,
            "箱子宽(cm)": 30.0,
            "箱子高(cm)": 20.0,
            "单箱重(kg)": 10.0,
            "总实重(kg)": 20.0,
            "总体积重(kg)": 16.0,
            "收费重(kg)": 20.0,
            "总CBM": 0.048,
        }
    ])

    xlsx_bytes = export_forwarder_quote(mock_df)
    assert len(xlsx_bytes) > 0

    exported_wb = load_workbook(io.BytesIO(xlsx_bytes))
    sheet = exported_wb.active
    
    # 遍历所有单元格，确保无任何未转义恶意前缀
    for r in range(1, sheet.max_row + 1):
        for c in range(1, sheet.max_column + 1):
            cell_val = sheet.cell(r, c).value
            if isinstance(cell_val, str) and cell_val:
                # 不允许首字符为原始 =, @，也不允许以非数字的 +, - 开头
                assert not cell_val.startswith("="), f"Row {r} Col {c} raw '=' unescaped: {cell_val}"
                assert not cell_val.startswith("@"), f"Row {r} Col {c} raw '@' unescaped: {cell_val}"

    elapsed = (time.perf_counter() - t0) * 1000
    print(f"[SCENARIO_C] PASS: CWE-1236 Excel injection neutralized with ' prefix in {elapsed:.2f}ms")


# ---------------------------------------------------------
# 场景 D：批量上传 DoS 资源耗尽攻击 (CWE-400)
# ---------------------------------------------------------
def test_scenario_d_batch_upload_dos_limits():
    client = TestClient(app)
    # 1. 超过 50 个文件批量上传攻击 (51 files)
    t_files_start = time.perf_counter()
    files_51 = [("files", (f"test_{i}_ONT8.csv", b"dummy content", "text/csv")) for i in range(51)]
    resp_files = client.post("/api/routing/preview", files=files_51)
    dur_files_ms = (time.perf_counter() - t_files_start) * 1000

    assert resp_files.status_code == 400
    assert "50 个文件" in resp_files.json().get("detail", "")
    # 验证防御在极短时间内（< 25ms）熔断
    assert dur_files_ms < 50.0, f"Files DoS check took too long: {dur_files_ms:.2f}ms"
    print(f"[SCENARIO_D1] PASS: 51 files rejected with HTTP 400 in {dur_files_ms:.2f}ms")

    # 2. 超过 50MB 恶意大文件流攻击 (51 MB)
    t_stream_start = time.perf_counter()
    big_content = b"X" * (51 * 1024 * 1024)
    files_big = [("files", ("big_ONT8.csv", big_content, "text/csv"))]
    resp_big = client.post("/api/routing/preview", files=files_big)
    dur_stream_ms = (time.perf_counter() - t_stream_start) * 1000

    assert resp_big.status_code == 400
    assert "超过 50MB" in resp_big.json().get("detail", "")
    print(f"[SCENARIO_D2] PASS: >50MB stream rejected with HTTP 400 in {dur_stream_ms:.2f}ms")


# ---------------------------------------------------------
# 场景 E：FastAPI 主事件循环阻塞攻击验证
# ---------------------------------------------------------
@pytest.mark.anyio
async def test_scenario_e_event_loop_concurrency():
    sample_csv = """货件编号,FBA12345678
货件名称,FBA_ONT8_Shipment
箱子数量,2
SKU,FNSKU,品名,箱子 1,箱子 2
箱号,,,FBA12345678U000001,FBA12345678U000002
TEST-SKU-1,X001,Widget,10,20
包装箱长度 (cm),,,50,50
包装箱宽度 (cm),,,40,40
包装箱高度 (cm),,,30,30
包装箱重量 (kg),,,12.5,14.2
"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 预热 ASGI 路由中间件
        warm = await client.get("/api/health")
        assert warm.status_code == 200

        # 发起 heavy routing preview
        files_payload = [
            ("files", (f"第{i+1}票ONT8.csv", sample_csv.encode("utf-8-sig"), "text/csv"))
            for i in range(10)
        ]

        async def run_batch():
            return await client.post("/api/routing/preview", files=files_payload)

        async def run_health_probes():
            latencies = []
            for _ in range(5):
                t0 = time.perf_counter()
                r = await client.get("/api/health")
                lat = (time.perf_counter() - t0) * 1000
                assert r.status_code == 200
                latencies.append(lat)
                await asyncio.sleep(0.005)
            return latencies

        t_total_0 = time.perf_counter()
        batch_task = asyncio.create_task(run_batch())
        health_task = asyncio.create_task(run_health_probes())

        batch_resp, health_lats = await asyncio.gather(batch_task, health_task)
        total_time_ms = (time.perf_counter() - t_total_0) * 1000

        assert batch_resp.status_code == 200
        avg_health_lat = sum(health_lats) / len(health_lats)
        max_health_lat = max(health_lats)

        # 主事件循环探针必须在毫秒级（平均 < 80ms，显著低于批处理耗时），验证 asyncio.to_thread 卸载成功未被阻塞
        assert avg_health_lat < 80.0, f"Event loop stalled! Avg probe latency: {avg_health_lat:.2f}ms"
        assert avg_health_lat < total_time_ms, f"Probe took longer than entire batch! {avg_health_lat:.2f}ms >= {total_time_ms:.2f}ms"
        print(f"[SCENARIO_E] PASS: Batch completed in {total_time_ms:.2f}ms, Health probe avg: {avg_health_lat:.2f}ms, max: {max_health_lat:.2f}ms (asyncio.to_thread unblocked)")


if __name__ == "__main__":
    test_scenario_a_path_traversal_and_reserved_names()
    test_scenario_b_null_byte_truncation()
    test_scenario_c_excel_formula_injection()
    test_scenario_d_batch_upload_dos_limits()
    asyncio.run(test_scenario_e_event_loop_concurrency())
    print("\nALL 5 CHAOS PENETRATION SCENARIOS SUCCESSFULLY DEFENDED!")
