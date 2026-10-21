"""V4 Phase A/B：快照、回写、任务、报关币种、领星表格、箱规与打包约束。"""
from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path

import openpyxl
import pytest
from openpyxl.worksheet.datavalidation import DataValidation

os.environ.setdefault("FBA_DISABLE_SCHEDULER", "1")

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
TEMPLATES = BACKEND / "templates" / "forwarders"
FORWARDERS = {
    "send": "send.xlsx",
    "qiluo": "qiluo.xlsx",
    "jiufang": "jiufang.xlsx",
    "qiluo_t5": "qiluo_t5.xlsx",
    "qiluo_t6": "qiluo_t6.xlsx",
    "deshu": "deshu_t3.xlsx",
}


def _bytes(name: str) -> bytes:
    return (TEMPLATES / name).read_bytes()


def _snapshot(name: str, clamp: bool = True):
    from fba_tool.univer_snapshot import workbook_to_snapshot

    return workbook_to_snapshot(_bytes(name), clamp=clamp)


def _rules(snapshot: dict) -> list:
    resources = snapshot.get("resources") or []
    import json

    for item in resources:
        if item.get("name") == "SHEET_DATA_VALIDATION_PLUGIN":
            return json.loads(item["data"])
    return {}


def _semantic(data: bytes) -> dict:
    wb = openpyxl.load_workbook(io.BytesIO(data))
    try:
        sheets = {}
        for ws in wb.worksheets:
            values = {}
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is not None:
                        values[cell.coordinate] = cell.value
            dvs = []
            for dv in ws.data_validations.dataValidation:
                dvs.append((str(dv.sqref), str(dv.type), str(dv.formula1), str(dv.formula2), str(dv.operator)))
            cfs = []
            for sqref, rules in ws.conditional_formatting._cf_rules.items():
                cfs.append((str(sqref), len(rules)))
            sheets[ws.title] = {
                "state": ws.sheet_state,
                "values": values,
                "merges": sorted(str(item) for item in ws.merged_cells.ranges),
                "dv": sorted(dvs),
                "images": len(getattr(ws, "_images", []) or []),
                "cf": sorted(cfs),
            }
        return sheets
    finally:
        wb.close()


def _diff(left: dict, right: dict) -> list:
    diffs = []
    for name in sorted(set(left) | set(right)):
        a = left.get(name)
        b = right.get(name)
        if a is None or b is None:
            diffs.append(f"sheet {name}")
            continue
        for key in ("state", "merges", "dv", "images", "cf"):
            if a[key] != b[key]:
                diffs.append(f"{name}.{key}")
        for coord in sorted(set(a["values"]) | set(b["values"])):
            if a["values"].get(coord) != b["values"].get(coord):
                diffs.append(f"{name}!{coord}")
    return diffs


def test_v4_t5_send_clamp_and_noclamp_stay_small():
    clamped = _snapshot("send.xlsx", True)["snapshot"]
    plain = _snapshot("send.xlsx", False)["snapshot"]
    for sheet in clamped["sheets"].values():
        assert sheet["rowCount"] < 100000
        assert sheet["rowCount"] != 1048576
    rules = _rules(clamped)
    million = []
    for sheet_rules in rules.values():
        for rule in sheet_rules:
            for item in rule["ranges"]:
                if item["endRow"] >= 100000:
                    million.append(item)
    assert million == []
    noclamp_rows = [sheet["rowCount"] for sheet in plain["sheets"].values()]
    assert max(noclamp_rows) < 1000
    huge = [
        item["endRow"]
        for sheet_rules in _rules(plain).values()
        for rule in sheet_rules
        for item in rule["ranges"]
        if item["endRow"] >= 1048570
    ]
    assert huge


def test_v4_t5b_hidden_sheets_and_formula1():
    # qiluo_t6 的四张表在模板里都是 visible。隐藏标记必须跟 Excel 一致，不能为了断言改成 hidden。
    for filename, expect_hidden in (("deshu_t3.xlsx", True), ("qiluo_t6.xlsx", False)):
        original = openpyxl.load_workbook(TEMPLATES / filename)
        snap = _snapshot(filename)["snapshot"]
        hidden = [sheet["name"] for sheet in snap["sheets"].values() if sheet.get("hidden") == 1]
        excel_hidden = [ws.title for ws in original.worksheets if ws.sheet_state != "visible"]
        assert hidden == excel_hidden
        assert bool(hidden) is expect_hidden
        expected = {}
        for ws in original.worksheets:
            for dv in ws.data_validations.dataValidation:
                if dv.formula1 not in (None, ""):
                    expected.setdefault(ws.title, []).append(str(dv.formula1))
        got = {}
        rules = _rules(snap)
        by_id = {sheet["id"]: sheet["name"] for sheet in snap["sheets"].values()}
        for sheet_id, sheet_rules in rules.items():
            got[by_id[sheet_id]] = [rule["formula1"] for rule in sheet_rules if rule.get("formula1")]
        for name, formulas in expected.items():
            assert formulas == got.get(name)
        original.close()


@pytest.mark.parametrize("forwarder", list(FORWARDERS))
def test_v4_roundtrip_and_single_cell_edit(forwarder):
    from fba_tool.univer_apply import apply_snapshot_values

    raw = _bytes(FORWARDERS[forwarder])
    payload = _snapshot(FORWARDERS[forwarder])
    same = apply_snapshot_values(raw, payload["snapshot"])
    assert _diff(_semantic(raw), _semantic(same)) == []

    snapshot = payload["snapshot"]
    edited = None
    for sheet in snapshot["sheets"].values():
        for row, cols in (sheet.get("cellData") or {}).items():
            for col, cell in cols.items():
                if not isinstance(cell, dict) or cell.get("f"):
                    continue
                if cell.get("v") in (None, ""):
                    continue
                cell["v"] = "V4-EDIT"
                cell["t"] = 1
                edited = (sheet["name"], int(row) + 1, int(col) + 1)
                break
            if edited:
                break
        if edited:
            break
    assert edited
    changed = apply_snapshot_values(raw, snapshot)
    diffs = _diff(_semantic(raw), _semantic(changed))
    from openpyxl.utils import get_column_letter

    coord = f"{edited[0]}!{get_column_letter(edited[2])}{edited[1]}"
    assert diffs == [coord]


def test_v4_t4_merged_slave_rejected():
    from fba_tool.univer_apply import ApplyRejected, apply_snapshot_values

    raw = _bytes("send.xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(raw))
    slave = None
    for ws in wb.worksheets:
        for merged in ws.merged_cells.ranges:
            if merged.max_row - merged.min_row + merged.max_col - merged.min_col > 0:
                slave = (ws.title, merged.min_row, merged.min_col + 1 if merged.max_col > merged.min_col else merged.min_row + 1 and merged.min_col)
                # 取范围内不是左上角的一格
                if merged.max_col > merged.min_col:
                    slave = (ws.title, merged.min_row, merged.min_col + 1)
                elif merged.max_row > merged.min_row:
                    slave = (ws.title, merged.min_row + 1, merged.min_col)
                else:
                    slave = None
                break
        if slave:
            break
    wb.close()
    assert slave
    payload = _snapshot("send.xlsx")["snapshot"]
    sheet = next(item for item in payload["sheets"].values() if item["name"] == slave[0])
    sheet.setdefault("cellData", {}).setdefault(str(slave[1] - 1), {})[str(slave[2] - 1)] = {"v": "SLAVE", "t": 1}
    with pytest.raises(ApplyRejected) as caught:
        apply_snapshot_values(raw, payload)
    assert caught.value.code == "MERGED_SLAVE"


def test_v4_t8_formula_plain_value_rejected_and_formula_kept():
    from fba_tool.univer_apply import ApplyRejected, apply_snapshot_values

    raw = _bytes("qiluo_t6.xlsx")
    payload = _snapshot("qiluo_t6.xlsx")["snapshot"]
    target = None
    for sheet in payload["sheets"].values():
        for row, cols in (sheet.get("cellData") or {}).items():
            for col, cell in cols.items():
                if isinstance(cell, dict) and cell.get("f"):
                    target = (sheet, row, col, cell["f"])
                    break
            if target:
                break
        if target:
            break
    assert target
    sheet, row, col, formula = target
    kept = apply_snapshot_values(raw, payload)
    assert _diff(_semantic(raw), _semantic(kept)) == []
    cell = sheet["cellData"][row][col]
    cell.pop("f", None)
    cell["v"] = "123"
    cell["t"] = 2
    with pytest.raises(ApplyRejected) as caught:
        apply_snapshot_values(raw, payload)
    assert caught.value.code == "FORMULA_OVERWRITE"
    assert caught.value.cells
    cell["f"] = formula + "+1"
    cell.pop("v", None)
    rewritten = apply_snapshot_values(raw, payload)
    assert _diff(_semantic(raw), _semantic(rewritten)) == []


def test_v4_t7_large_sheet_job_progress_and_cancel(monkeypatch):
    from fastapi.testclient import TestClient

    from fba_tool.univer_snapshot import SnapshotCancelled
    from main import app

    state = {"calls": 0}

    def slow(data, clamp=True, progress=None, cancel_event=None):
        state["calls"] += 1
        for step in range(20):
            if cancel_event is not None and cancel_event.is_set():
                raise SnapshotCancelled()
            if progress:
                progress(step * 5)
            time.sleep(0.05)
        return {"snapshot": {"id": "wb", "sheets": {}}, "meta": {"used_rows": 6001}}

    monkeypatch.setattr("fba_tool.univer_snapshot.estimate_used_rows", lambda data: 6001)
    monkeypatch.setattr("fba_tool.univer_snapshot.workbook_to_snapshot", slow)
    client = TestClient(app)
    started = time.perf_counter()
    response = client.post("/api/univer/snapshot", data={"forwarder_id": "send"})
    assert time.perf_counter() - started < 2
    assert response.status_code == 202
    body = response.json()
    assert body["status"] in {"queued", "running", "cancelled"}
    job_id = body["job_id"]
    seen = client.get(f"/api/jobs/{job_id}")
    assert seen.status_code == 200
    cancelled = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    deadline = time.time() + 3
    status = cancelled.json()["status"]
    while status in {"queued", "running"} and time.time() < deadline:
        status = client.get(f"/api/jobs/{job_id}").json()["status"]
        time.sleep(0.05)
    assert status == "cancelled"


def test_v4_t7_sync_template_returns_without_blocking_past_two_seconds():
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    started = time.perf_counter()
    response = client.post("/api/univer/snapshot", data={"forwarder_id": "send"})
    elapsed = time.perf_counter() - started
    assert response.status_code == 200
    assert elapsed < 2
    assert response.json()["snapshot"]["sheets"]


def test_v4_c1_export_send_keeps_model_name_wu_and_records_fx():
    from fba_tool.invoice_export import export_invoice
    from fba_tool.shipment_parser import parse_csv_shipment

    csv_text = "\n".join([
        '"货件编号","FBATESTMIX01"',
        '"货件名称","TEST-LAX9"',
        '"配送地址","FONTANA, CA"',
        '"箱子数量","1"',
        "",
        '"多件商品（1 箱）"',
        '"SKU","商品名称","ASIN","FNSKU","状况","预处理类型","商品总数","箱子 1 的商品数量"',
        '"S-A","a","B0A","X00TEST0AA","新品","无","4","4"',
        "",
        '"","","","","","","箱号","FBATESTMIX01U000001"',
        '"","","","","","","包装箱重量（磅）：","10"',
        '"","","","","","","包装箱长度（英寸）：","10"',
        '"","","","","","","包装箱宽度（英寸）：","10"',
        '"","","","","","","包装箱高度（英寸）：","10"',
    ]).encode("utf-8")
    shipment = parse_csv_shipment(csv_text, file_name="mix.csv")
    product = {
        "fnsku": "X00TEST0AA",
        "listing_price": 10.0,
        "english_name": "Item",
        "chinese_name": "物品",
        "brand": "B",
        "material": "铁",
        "purpose": "用",
        "hs_code": "7326909000",
        "asin": "B0X",
        "model_name": "无",
        "invoice": {"unit": "个", "purchase_price": 5, "material_en": "iron", "purpose_en": "use", "pcs_per_set": 1},
    }
    result = export_invoice("send", shipment=shipment, products={"X00TEST0AA": product}, reference_id="R1", invoice_date="2026-10-21")
    assert result["bytes"][:2] == b"PK"
    assert result["model"].meta["fx"]["fx_pair"] == "USD/CNY"
    blank = dict(product, model_name="")
    from fba_tool.invoice_rules import InvoiceBlocked

    with pytest.raises(InvoiceBlocked):
        export_invoice("send", shipment=shipment, products={"X00TEST0AA": blank}, reference_id="R1")


def test_v4_c1_customs_currency_and_model_blank():
    from fba_tool.export_compliance import review_products
    from fba_tool.fx_rates import upsert_rate

    product = {
        "chinese_name": "垫",
        "material": "布",
        "purpose": "宠物",
        "brand": "Joy",
        "model_name": "无",
        "hs_code": "630790",
        "product_cost_currency": "CNY",
        "listing_price_currency": "USD",
    }
    blockers, trace = review_products({"SKU": product}, "2026-10-21")
    assert blockers == []
    blank = dict(product, model_name="")
    blockers, _trace = review_products({"SKU": blank}, "2026-10-21")
    assert any(item["field"] == "model_name" for item in blockers)
    usd_cost = dict(product, product_cost_currency="USD")
    blockers, _trace = review_products({"SKU": usd_cost}, "2026-10-21")
    assert any(item["code"] == "cost_currency_mismatch" for item in blockers)
    cad = dict(product, listing_price_currency="CAD")
    blockers, _trace = review_products({"SKU": cad}, "2026-10-21")
    assert any(item["code"] == "retail_currency_mismatch" for item in blockers)
    upsert_rate({
        "currency_pair": "USD/CNY",
        "rate": 7.1,
        "rate_type": "customs_monthly",
        "applicable_month": "2026-10",
        "publish_date": "2026-10-01",
        "source": "测试海关月汇率",
    })
    _blockers, trace = review_products({"SKU": product}, "2026-10-21")
    assert trace["fx_source"] == "测试海关月汇率"
    assert trace["fx_publish_date"] == "2026-10-01"


def test_v4_a6_frozen_exe_data_dir_beside_exe(tmp_path, monkeypatch):
    from fba_tool import app_paths

    exe = tmp_path / "exe"
    local = tmp_path / "local"
    exe.mkdir()
    monkeypatch.delenv("FBA_APP_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(app_paths, "project_root", lambda: exe)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert app_paths.app_data_dir() == exe / "app_data"
    assert (exe / "app_data").is_dir()
    assert not (local / "FBA_Smart_Tool").exists()


def test_v4_a6_upx_disabled():
    text = (ROOT / "packaging" / "FBA_Smart_Tool.spec").read_text(encoding="utf-8")
    assert "upx=True" not in text
    assert text.count("upx=False") >= 2


def test_v4_a7_dependency_scan():
    import subprocess

    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_spreadsheet_deps.py")], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def _wipe_listing(skus: list[str], run_ids: list[int]) -> None:
    from fba_tool.master_db import _connect

    with _connect() as conn:
        for run_id in run_ids:
            conn.execute("DELETE FROM lingxing_sync_diff WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM lingxing_sync_preview_field WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM lingxing_sync_preview_sku WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM lingxing_sync_run WHERE id = ?", (run_id,))
        for sku in skus:
            conn.execute("DELETE FROM product_field_history WHERE sku = ?", (sku,))
            conn.execute("DELETE FROM product_master WHERE sku = ?", (sku,))
        conn.commit()


def _synthetic_listing_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "sheet1"
    ws.append([
        "MSKU", "FNSKU", "ASIN", "父ASIN", "状态", "店铺", "国家", "配送方式",
        "币种", "价格", "优惠价", "售价(总价)", "List Price", "划线价",
        "预估FBA费（API）", "平台费率", "SKU", "品名", "标题", "亚马逊品牌", "大类名称",
    ])
    ws.append([
        "SYN-MAT-1", "X00TESTMAT", "B0SYNMAT01", "B0SYNPARENT", "在售", "Shop-US", "美国", "FBA",
        "USD", 37.99, 37.99, 37.99, 39.99, 39.99,
        8.93, "15.0%", "SYN-LOCAL", "本地品名不入库", "English title", "AmazonBrand", "Pet Supplies",
    ])
    ws.append([
        "SYN-MAT-2", "X00TESTMA2", "B0SYNMAT02", "B0SYNPARENT", "在售", "Shop-US", "美国", "FBM",
        "USD", 12, 12, 12, 14, 14,
        3.2, 0.15, "SYN-LOCAL", "另一条本地名", "Other title", "AmazonBrand", "Pet Supplies",
    ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_v4_d1_listing_preview_confirm_rollback():
    from fastapi.testclient import TestClient

    from fba_tool.lingxing_listing_xlsx import parse_listing_xlsx
    from fba_tool.master_db import get_product_by_sku, upsert_product
    from fba_tool.product_fields import SOURCE_MANUAL, mark_field_sources, set_product_fields
    from main import app

    data = _synthetic_listing_xlsx()
    filename = "synthetic-us-listing-2026-10-21.xlsx"
    parsed = parse_listing_xlsx(data, filename)
    assert parsed["export_at"] == "2026-10-21"
    assert len(parsed["products"]) == 2
    assert any("SYN-LOCAL" in item and "2 个 MSKU" in item for item in parsed["warnings"])
    sample = next(item for item in parsed["products"] if item["sku"] == "SYN-MAT-1")
    assert sample["listing_price_currency"] == "USD"
    assert sample["listing_price_site"] == "US"
    assert sample["listing_price"] == 37.99
    assert sample["fee_fba_est"] == 8.93
    assert sample["fee_referral_rate"] == pytest.approx(0.15)
    assert sample["local_sku"] == "SYN-LOCAL"
    assert "chinese_name" not in sample
    assert "brand" not in sample
    assert "english_name" not in sample
    skus = [item["sku"] for item in parsed["products"]]
    run_ids: list[int] = []
    try:
        upsert_product({
            "sku": sample["sku"],
            "chinese_name": "手填品名",
            "material": "手填材质",
            "carton_length": 40,
        })
        set_product_fields(sample["sku"], {"listing_price": 1, "listing_price_currency": "USD"}, SOURCE_MANUAL)
        mark_field_sources(sample["sku"], ["chinese_name", "material", "carton_length"], SOURCE_MANUAL)
        client = TestClient(app)
        before = get_product_by_sku(sample["sku"])
        response = client.post(
            "/api/lingxing/import-xlsx",
            files={"file": (filename, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert response.status_code == 200
        body = response.json()
        run_ids.append(body["run_id"])
        assert body["wrote_product_master"] is False
        assert body["export_at"] == "2026-10-21"
        assert get_product_by_sku(sample["sku"])["chinese_name"] == before["chinese_name"]
        preview = client.get("/api/lingxing/sync/preview", params={"run_id": body["run_id"]}).json()
        items = []
        for rows in preview["groups"].values():
            for row in rows:
                fields = [field["field"] for field in row.get("fields") or [] if field.get("default_checked")]
                if "carton_length" in fields or "chinese_name" in fields or "material" in fields:
                    raise AssertionError(fields)
                if fields:
                    items.append({"sku": row["sku"], "fields": fields})
        confirmed = client.post("/api/lingxing/sync/confirm", json={"run_id": body["run_id"], "items": items})
        assert confirmed.status_code == 200
        saved = get_product_by_sku(sample["sku"])
        assert saved["chinese_name"] == "手填品名"
        assert saved["material"] == "手填材质"
        assert saved["carton_length"] == 40
        assert saved["listing_price"] == 37.99
        assert saved["listing_price_currency"] == "USD"
        again = client.post(
            "/api/lingxing/import-xlsx",
            files={"file": (filename, data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        run_ids.append(again.json()["run_id"])
        second_items = []
        second_preview = client.get("/api/lingxing/sync/preview", params={"run_id": again.json()["run_id"]}).json()
        for rows in second_preview["groups"].values():
            for row in rows:
                fields = [field["field"] for field in row.get("fields") or [] if field.get("default_checked")]
                if fields:
                    second_items.append({"sku": row["sku"], "fields": fields})
        assert client.post("/api/lingxing/sync/confirm", json={"run_id": again.json()["run_id"], "items": second_items}).status_code == 200
        from fba_tool.master_db import _connect

        with _connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM product_master WHERE sku = ?", (sample["sku"],)).fetchone()[0]
        assert count == 1
        rolled = client.post(f"/api/lingxing/runs/{body['run_id']}/rollback")
        assert rolled.status_code == 200
        restored = get_product_by_sku(sample["sku"])
        assert restored["listing_price"] == 1
        assert restored["chinese_name"] == "手填品名"
    finally:
        _wipe_listing(skus, run_ids)


def test_v4_d1_owner_listing_shape_when_present():
    """本机上传的美国站导出只在文件还在时核对形状，不把货号写进仓库。"""
    from fba_tool.lingxing_listing_xlsx import parse_listing_xlsx

    upload = Path("/home/ubuntu/.cursor/projects/workspace/uploads/lingxing_listing_export_2026-10-21_4126.xlsx")
    if not upload.is_file():
        pytest.skip("owner listing export is not on this machine")
    parsed = parse_listing_xlsx(upload.read_bytes(), upload.name)
    assert parsed["export_at"] == "2026-10-21"
    assert len(parsed["products"]) == 44
    assert parsed["warnings"]
    assert {item.get("listing_price_currency") for item in parsed["products"]} == {"USD"}
    assert {item.get("listing_price_site") for item in parsed["products"]} == {"US"}
    assert all("chinese_name" not in item and "brand" not in item and "english_name" not in item for item in parsed["products"])
    assert any(item.get("fee_fba_est") for item in parsed["products"])
    assert any(item.get("fee_referral_rate") == pytest.approx(0.15) for item in parsed["products"])


def test_v4_d1_currency_anomaly_keeps_other_rows_and_exports_errors():
    from fastapi.testclient import TestClient

    from fba_tool.lingxing_listing_xlsx import parse_listing_xlsx
    from main import app

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["MSKU", "国家", "币种", "价格", "采购成本", "成本币种", "品名"])
    ws.append(["US-1", "美国", "USD", 12.5, 30, "CNY", "本地名"])
    ws.append(["CA-1", "加拿大", "USD", 9, None, None, "加拿大名"])
    ws.append(["US-2", "美国", "USD", 8, 10, "USD", "成本美元"])
    buf = io.BytesIO()
    wb.save(buf)
    parsed = parse_listing_xlsx(buf.getvalue(), "lingxing_listing_export_2026-10-21.xlsx")
    skus = {item["sku"]: item for item in parsed["products"]}
    assert skus["US-1"]["listing_price"] == 12.5
    assert skus["US-1"]["listing_price_currency"] == "USD"
    assert skus["US-1"]["product_cost_cny"] == 30
    assert "CA-1" not in skus
    assert "US-2" in skus
    assert "product_cost_cny" not in skus["US-2"]
    assert any(item["sku"] == "CA-1" for item in parsed["anomalies"])
    client = TestClient(app)
    response = client.post(
        "/api/lingxing/import-xlsx",
        files={"file": ("lingxing_listing_export_2026-10-21.xlsx", buf.getvalue(), "application/octet-stream")},
    )
    run_id = response.json()["run_id"]
    try:
        csv_text = client.get(f"/api/lingxing/runs/{run_id}/errors.csv").text
        assert "CA-1" in csv_text
        assert "US-2" in csv_text
    finally:
        _wipe_listing(["US-1", "US-2", "CA-1"], [run_id])


def test_v4_d2_readonly_schedule_and_absent_sku_kept(monkeypatch):
    from fba_tool.lingxing_scheduler import DEFAULTS, ReadOnlyClient, ReadOnlyViolation, load_schedule, read_log_tail, run_once, sync_logger
    from fba_tool.master_db import get_product_by_sku, upsert_product

    assert DEFAULTS["enabled"] is False
    assert load_schedule()["enabled"] is False
    client = ReadOnlyClient(object())
    with pytest.raises(ReadOnlyViolation):
        client.action("listing_update", {})
    result = run_once(trigger="scheduled", sleep=lambda _seconds: None)
    assert result["ok"] is False
    assert result["status"] == "failed"
    sync_logger().info("v4 d2 log marker")
    assert any("v4 d2 log marker" in line or "MCP Key" in line for line in read_log_tail(50))
    upsert_product({"sku": "KEEP-ME", "chinese_name": "留下"})
    try:
        assert get_product_by_sku("KEEP-ME")["chinese_name"] == "留下"
        text = (BACKEND / "fba_tool" / "lingxing_sync.py").read_text(encoding="utf-8")
        assert "DELETE FROM product_master" not in text
        assert get_product_by_sku("KEEP-ME")["chinese_name"] == "留下"
    finally:
        from fba_tool.master_db import delete_product_by_sku

        delete_product_by_sku("KEEP-ME")


def test_v4_b2_oversize_does_not_block_existing_api_limit():
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    ok = client.post("/api/carton-specs", json={
        "sku": "V4-OVER",
        "length_cm": 70,
        "width_cm": 40,
        "height_cm": 30,
        "qty_per_carton": 4,
        "gross_kg": 24,
        "source": "manual",
    })
    assert ok.status_code == 200
    blocked = client.post("/api/carton-specs", json={
        "sku": "V4-HEAVY",
        "length_cm": 40,
        "width_cm": 40,
        "height_cm": 40,
        "qty_per_carton": 1,
        "gross_kg": 80,
        "source": "manual",
    })
    assert blocked.status_code == 422
    missing = client.post("/api/carton-specs", json={"sku": "", "gross_kg": 1})
    assert missing.status_code == 422


def test_forwarder_dropdown_includes_invoice_templates():
    from fba_tool.forwarder_registry import get_template_bytes, list_forwarders

    ids = {item.id for item in list_forwarders()}
    for forwarder_id in ("qiluo_t5", "qiluo_t6", "deshu", "send"):
        assert forwarder_id in ids
        assert get_template_bytes(forwarder_id)


def test_deshu_currency_dropdown_survives_snapshot_apply():
    from fba_tool.univer_apply import apply_snapshot_values

    raw = _bytes("deshu_t3.xlsx")
    out = apply_snapshot_values(raw, _snapshot("deshu_t3.xlsx")["snapshot"])
    before = _semantic(raw)["发票填写模板"]["dv"]
    after = _semantic(out)["发票填写模板"]["dv"]
    assert before == after
    assert any("USD" in item[2] for item in after)
