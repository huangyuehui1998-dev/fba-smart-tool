"""测试方 r2：琪珞型号/材质分列、SEND 明细区与主格、预览改动导出、回滚 NULL、脱敏第 13 批。"""
from __future__ import annotations

import base64
import io
import json
from datetime import datetime, timezone

import openpyxl
import pytest

FORWARDERS = ("send", "jiufang", "qiluo", "qiluo_t5", "qiluo_t6", "deshu")


def _csv(shipment: str, sku: str, fnsku: str, asin: str) -> bytes:
    return "\n".join([
        f'"货件编号","{shipment}"',
        '"货件名称","B13-DESENS"',
        '"配送地址","STEP45VILLE, ZZ"',
        '"箱子数量","1"',
        "",
        '"单件商品（1 箱）"',
        '"SKU","商品名称","ASIN","FNSKU","状况","预处理类型","商品总数","箱子 1 的商品数量"',
        f'"{sku}","rod","{asin}","{fnsku}","新品","无","4","4"',
        "",
        f'"","","","","","","箱号","{shipment}U000001"',
        '"","","","","","","包装箱重量（磅）：","10"',
        '"","","","","","","包装箱长度（英寸）：","17.70"',
        '"","","","","","","包装箱宽度（英寸）：","17.70"',
        '"","","","","","","包装箱高度（英寸）：","16.10"',
    ]).encode("utf-8")


def _seed(sku: str, fnsku: str, asin: str, model_name: str, material: str = "塑料", purpose: str = "户外"):
    from fba_tool.master_db import _connect, init_master_db, upsert_product
    from fba_tool.product_fields import SOURCE_MANUAL, set_product_fields

    init_master_db()
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute("DELETE FROM fba_warehouse WHERE code = ?", ("TST1",))
        conn.execute(
            """
            INSERT INTO fba_warehouse
                (code, name, company, address1, city, state, zip, country, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("TST1", "TST1", "Amazon", "1 Test Road", "STEP45VILLE", "ZZ", "00000", "US", now),
        )
        conn.commit()
    upsert_product(
        {
            "sku": sku,
            "fnsku": fnsku,
            "asin": asin,
            "english_name": "Fishing rod",
            "chinese_name": "鱼竿",
            "brand": "Acme",
            "material": material,
            "purpose": purpose,
            "hs_code": "9507100090",
            "model_name": model_name,
            "extra_data": json.dumps(
                {"invoice": {"unit": "个", "purchase_price": 5, "material_en": "plastic", "purpose_en": "outdoor", "pcs_per_set": 1}},
                ensure_ascii=False,
            ),
        }
    )
    set_product_fields(sku, {"listing_price": 12.5, "listing_price_currency": "USD"}, SOURCE_MANUAL)


def _book(data: bytes):
    return openpyxl.load_workbook(io.BytesIO(data))


@pytest.mark.parametrize("forwarder_id", FORWARDERS)
def test_desensitized_batch13_fill_then_export(forwarder_id):
    """脱敏第 13 批形状：Step 4.5 生成再导出，六个模板都要 200，且明细写进表里。"""
    from fastapi.testclient import TestClient

    from fba_tool.master_db import delete_product_by_sku
    from main import app

    sku, fnsku, asin = "B13-SKU", "X00B13E2E1", "B0B13DS001"
    _seed(sku, fnsku, asin, "型号乙")
    raw = _csv("FBA13DS01", sku, fnsku, asin)
    client = TestClient(app)
    try:
        generated = client.post(
            "/api/invoice/generate",
            json={
                "shipment_id": "FBA13DS01",
                "forwarder_id": forwarder_id,
                "csv_base64": base64.b64encode(raw).decode(),
                "po_number": "PO-13",
            },
        )
        assert generated.status_code == 200, generated.text
        body = generated.json()
        cells = {item["cell"]: item.get("value") for item in body["cells"]}
        if forwarder_id == "qiluo":
            assert cells.get("K2") == "型号乙"
            assert cells.get("H2") == "塑料"
            assert cells.get("I2") == "户外"
            assert "/" not in str(cells.get("H2") or "")
            assert sku not in cells.values()
        if forwarder_id == "send":
            assert "B4" not in cells and "B5" not in cells and "B6" not in cells and "E5" not in cells
            assert cells.get("C4") == "FBA13DS01"
            assert fnsku in cells.values()
        exported = client.post(
            "/api/export_invoice",
            json={
                "template_hash": body["template_hash"],
                "forwarder_id": forwarder_id,
                "shipment_id": body["shipment_id"],
                "warehouse_code": body["warehouse_code"],
                "template_sheet": body["template_sheet"],
                "fields": body["cells"],
            },
        )
        assert exported.status_code == 200, exported.text[:400]
        assert exported.content[:2] == b"PK"
        wb = _book(exported.content)
        try:
            texts = {
                str(cell.value).strip()
                for ws in wb.worksheets
                for row in ws.iter_rows(max_row=min(ws.max_row or 1, 80), max_col=min(ws.max_column or 1, 24))
                for cell in row
                if cell.value not in (None, "")
            }
            assert "FBA13DS01" in texts
            if forwarder_id == "qiluo":
                assert wb.active["K2"].value == "型号乙"
                assert wb.active["H2"].value == "塑料"
                assert wb.active["I2"].value == "户外"
            if forwarder_id == "send":
                assert wb.active["C4"].value == "FBA13DS01"
                assert "FBA Shipment ID" in str(wb.active["A4"].value)
                assert fnsku in texts
        finally:
            wb.close()
    finally:
        delete_product_by_sku(sku)


def test_qiluo_empty_model_name_does_not_fall_back_to_sku():
    from fastapi.testclient import TestClient

    from fba_tool.master_db import delete_product_by_sku
    from main import app

    sku = "B13-NOMODEL"
    _seed(sku, "X00B13NONE", "B0B13NONE1", "")
    raw = _csv("FBA13NONE", sku, "X00B13NONE", "B0B13NONE1")
    client = TestClient(app)
    try:
        generated = client.post(
            "/api/invoice/generate",
            json={
                "shipment_id": "FBA13NONE",
                "forwarder_id": "qiluo",
                "csv_base64": base64.b64encode(raw).decode(),
            },
        )
        assert generated.status_code == 200, generated.text
        cells = {item["cell"]: item.get("value") for item in generated.json()["cells"]}
        assert cells.get("K2") in (None, "")
        assert sku not in set(cells.values())
        assert cells.get("H2") == "塑料"
        assert cells.get("I2") == "户外"
        assert "/" not in str(cells.get("H2") or "")
    finally:
        delete_product_by_sku(sku)


def test_export_keeps_preview_edits_and_official_shell():
    from fastapi.testclient import TestClient

    from fba_tool.forwarder_registry import get_template_bytes
    from main import app

    official = get_template_bytes("qiluo")
    wb = _book(official)
    wb.active["K2"] = "手改型号"
    wb.active["H2"] = "手改材质"
    wb.create_sheet("不应出现")
    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    client = TestClient(app)
    exported = client.post(
        "/api/export_invoice",
        json={
            "forwarder_id": "qiluo",
            "template_base64": base64.b64encode(buf.getvalue()).decode(),
            "shipment_id": "FBA13SHELL",
            "warehouse_code": "TST1",
            "template_sheet": "发票",
            "fields": [],
        },
    )
    assert exported.status_code == 200, exported.text[:400]
    out = _book(exported.content)
    try:
        assert "不应出现" not in out.sheetnames
        assert out.active["K2"].value == "手改型号"
        assert out.active["H2"].value == "手改材质"
        assert out.active["A1"].value == "箱序号*"
        assert str(out.active["K1"].value).startswith("型号")
    finally:
        out.close()


def test_export_field_edit_overrides_rendered_qiluo_model():
    from fastapi.testclient import TestClient

    from fba_tool.master_db import delete_product_by_sku
    from main import app

    sku = "B13-EDIT"
    _seed(sku, "X00B13EDIT", "B0B13EDIT1", "型号乙")
    raw = _csv("FBA13EDIT", sku, "X00B13EDIT", "B0B13EDIT1")
    client = TestClient(app)
    try:
        generated = client.post(
            "/api/invoice/generate",
            json={
                "shipment_id": "FBA13EDIT",
                "forwarder_id": "qiluo",
                "csv_base64": base64.b64encode(raw).decode(),
            },
        )
        assert generated.status_code == 200, generated.text
        body = generated.json()
        fields = [dict(item) for item in body["cells"]]
        for item in fields:
            if item.get("cell") == "K2":
                item["value"] = "预览改过"
        exported = client.post(
            "/api/export_invoice",
            json={
                "template_hash": body["template_hash"],
                "forwarder_id": "qiluo",
                "shipment_id": body["shipment_id"],
                "warehouse_code": body["warehouse_code"],
                "template_sheet": body["template_sheet"],
                "fields": fields,
            },
        )
        assert exported.status_code == 200, exported.text[:400]
        wb = _book(exported.content)
        try:
            assert wb.active["K2"].value == "预览改过"
            assert wb.active["H2"].value == "塑料"
        finally:
            wb.close()
    finally:
        delete_product_by_sku(sku)


def test_send_note_slave_does_not_fail_export():
    from fastapi.testclient import TestClient

    from fba_tool.forwarder_registry import get_template_bytes
    from main import app

    official = get_template_bytes("send")
    client = TestClient(app)
    exported = client.post(
        "/api/export_invoice",
        json={
            "forwarder_id": "send",
            "template_base64": base64.b64encode(official).decode(),
            "shipment_id": "FBA13NOTE",
            "warehouse_code": "",
            "template_sheet": "Sheet1",
            "fields": [{"cell": "E5", "value": "NOPE", "key": "E5", "label": "E5"}],
        },
    )
    assert exported.status_code == 200, exported.text[:400]
    wb = _book(exported.content)
    try:
        assert "澳洲" in str(wb.active["D5"].value)
        assert wb.active["I5"].value != "NOPE"
    finally:
        wb.close()


def test_rollback_restores_sql_null_not_empty_text(monkeypatch, tmp_path):
    from fba_tool.lingxing_rollback import record_import_changes, rollback_lingxing_run
    from fba_tool.master_db import _connect, delete_product_by_sku, get_product_by_sku, init_master_db, upsert_product
    from fba_tool.master_db_lingxing import create_lingxing_sync_run, finish_lingxing_sync_run
    from fba_tool.product_fields import SOURCE_LINGXING, set_product_fields

    ad = tmp_path / "app"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    init_master_db()
    sku = "RB-NULL-B13"
    delete_product_by_sku(sku)
    upsert_product({"sku": sku})
    with _connect() as conn:
        raw = conn.execute(
            "SELECT asin, english_name, brand, local_name, field_source_json FROM product_master WHERE sku = ?",
            (sku,),
        ).fetchone()
    assert list(raw) == [None, None, None, None, None]
    before = get_product_by_sku(sku)
    run_id = create_lingxing_sync_run()
    finish_lingxing_sync_run(run_id, "confirmed", [], {})
    changed = dict(before)
    changed["asin"] = "B0NULLB13"
    changed["english_name"] = "Temp"
    changed["brand"] = "Brand"
    upsert_product(changed, overwrite=True)
    set_product_fields(sku, {"local_name": "本地名"}, SOURCE_LINGXING)
    record_import_changes(run_id, sku, before, get_product_by_sku(sku))
    rollback_lingxing_run(run_id)
    with _connect() as conn:
        restored = conn.execute(
            "SELECT asin, english_name, brand, local_name, field_source_json FROM product_master WHERE sku = ?",
            (sku,),
        ).fetchone()
    assert list(restored) == [None, None, None, None, None]
    delete_product_by_sku(sku)
