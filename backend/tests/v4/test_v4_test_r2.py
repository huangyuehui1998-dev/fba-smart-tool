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


def _seed(
    sku: str,
    fnsku: str,
    asin: str,
    model_name: str,
    material: str = "塑料",
    purpose: str = "户外",
    declared_value: float | None = None,
    english_name: str = "Fishing rod",
):
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
            "english_name": english_name,
            "chinese_name": "鱼竿",
            "brand": "Acme",
            "material": material,
            "purpose": purpose,
            "hs_code": "9507100090",
            "model_name": model_name,
            "declared_value": declared_value,
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

    sku, fnsku, asin = "B13-SKU", "X00TESTE2E", "B0B13DS001"
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
    _seed(sku, "X00TESTNON", "B0B13NONE1", "")
    raw = _csv("FBA13NONE", sku, "X00TESTNON", "B0B13NONE1")
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
    _seed(sku, "X00TESTEDT", "B0B13EDIT1", "型号乙")
    raw = _csv("FBA13EDIT", sku, "X00TESTEDT", "B0B13EDIT1")
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


def test_send_note_slave_is_rejected():
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
    assert exported.status_code == 400, exported.text[:400]
    assert exported.json()["detail"]["code"] == "MERGED_SLAVE"
    assert "E5" in exported.json()["detail"]["cells"]


def test_send_step45_empty_reference_id_asks_for_pdf():
    from fastapi.testclient import TestClient

    from fba_tool.invoice_step45 import REFERENCE_ID_EMPTY_HINT
    from fba_tool.master_db import delete_product_by_sku
    from main import app

    sku = "B13-REF"
    delete_product_by_sku(sku)
    _seed(sku, "X00TESTREF", "B0B13REF01", "型号乙")
    raw = _csv("FBA13REF1", sku, "X00TESTREF", "B0B13REF01")
    client = TestClient(app)
    try:
        generated = client.post(
            "/api/invoice/generate",
            json={
                "shipment_id": "FBA13REF1",
                "forwarder_id": "send",
                "csv_base64": base64.b64encode(raw).decode(),
            },
        )
        assert generated.status_code == 200, generated.text[:400]
        assert REFERENCE_ID_EMPTY_HINT in (generated.json().get("warnings") or [])
    finally:
        delete_product_by_sku(sku)


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


def _range_boxes(label: str) -> int:
    text = str(label)
    if "-" not in text:
        return 1
    start, end = text.split("-", 1)
    return int(end) - int(start) + 1


def _multi_sku_csv() -> bytes:
    return "\n".join([
        '"货件编号","FBA13DS01"',
        '"货件名称","B13-DESENS"',
        '"配送地址","STEP45VILLE, ZZ"',
        '"箱子数量","4"',
        "",
        '"多件商品（4 箱）"',
        '"SKU","商品名称","ASIN","FNSKU","状况","预处理类型","商品总数","箱子 1 的商品数量","箱子 2 的商品数量","箱子 3 的商品数量","箱子 4 的商品数量"',
        '"B13-AAA","rod","B0B13AAA1","X00TESTAAA","新品","无","4","2","2","",""',
        '"B13-TANZI","rod","B0B13TNZ1","X00TESTTNZ","新品","无","4","","","2","2"',
        "",
        '"","","","","","","箱号","FBA13DS01U000001","FBA13DS01U000002","FBA13DS01U000003","FBA13DS01U000004"',
        '"","","","","","","包装箱重量（磅）：","10","10","10","10"',
        '"","","","","","","包装箱长度（英寸）：","17.70","17.70","17.70","17.70"',
        '"","","","","","","包装箱宽度（英寸）：","17.70","17.70","17.70","17.70"',
        '"","","","","","","包装箱高度（英寸）：","16.10","16.10","16.10","16.10"',
    ]).encode("utf-8")


def test_qiluo_multi_sku_rows_and_declared_total():
    """同一型号的两个 SKU 各占一行，申报总额含 TANZI 的 49.99。"""
    from fastapi.testclient import TestClient

    from fba_tool.master_db import delete_product_by_sku
    from main import app

    skus = (
        ("B13-AAA", "X00TESTAAA", "B0B13AAA1", 10),
        ("B13-TANZI", "X00TESTTNZ", "B0B13TNZ1", 49.99),
    )
    for sku, fnsku, asin, price in skus:
        delete_product_by_sku(sku)
        _seed(sku, fnsku, asin, "共用型号", declared_value=price)
    raw = _multi_sku_csv()
    client = TestClient(app)
    try:
        generated = client.post(
            "/api/invoice/generate",
            json={
                "shipment_id": "FBA13DS01",
                "forwarder_id": "qiluo",
                "csv_base64": base64.b64encode(raw).decode(),
            },
        )
        assert generated.status_code == 200, generated.text
        cells = generated.json()["cells"]
        by_field: dict[str, list] = {}
        for item in cells:
            by_field.setdefault(item.get("field_key"), []).append(item.get("value"))
        assert by_field.get("box_range") == ["1-2", "3-4"]
        assert by_field.get("model") == ["共用型号", "共用型号"]
        prices = [float(value) for value in by_field.get("declared_price") or []]
        qty = [float(value) for value in by_field.get("qty_per_box") or []]
        assert prices == [10.0, 49.99]
        assert qty == [2.0, 2.0]
        total = sum(price * per * _range_boxes(label) for price, per, label in zip(prices, qty, by_field["box_range"]))
        assert round(total, 2) == 239.96
        located = {item["cell"]: item.get("value") for item in cells}
        assert located.get("K2") == "共用型号"
        assert located.get("K3") == "共用型号"
        assert located.get("G2") == 10 or located.get("G2") == 10.0
        assert float(located.get("G3")) == 49.99
    finally:
        for sku, *_rest in skus:
            delete_product_by_sku(sku)


def test_send_and_jiufang_take_asin_from_csv_when_product_asin_is_empty():
    from fastapi.testclient import TestClient

    from fba_tool.master_db import delete_product_by_sku, get_product_by_sku
    from main import app

    sku, fnsku, asin = "B13-NOASIN", "X00TESTNAS", "B0CSVASIN1"
    delete_product_by_sku(sku)
    _seed(sku, fnsku, "", "型号乙")
    raw = _csv("FBA13DS01", sku, fnsku, asin)
    client = TestClient(app)
    try:
        for forwarder_id in ("send", "jiufang"):
            generated = client.post(
                "/api/invoice/generate",
                json={
                    "shipment_id": "FBA13DS01",
                    "forwarder_id": forwarder_id,
                    "csv_base64": base64.b64encode(raw).decode(),
                },
            )
            assert generated.status_code == 200, f"{forwarder_id} {generated.text}"
            assert "缺发票必填字段" not in generated.text
        exported = client.post(
            "/api/invoice-export/export",
            data={"forwarder_id": "send", "reference_id": "R"},
            files={"csv_file": ("ship.csv", raw, "text/csv")},
        )
        assert exported.status_code == 200, exported.text[:400]
        wb = _book(exported.content)
        try:
            sheet = next(ws for ws in wb.worksheets if "Invoice" in ws.title)
            assert sheet["N15"].value == asin
        finally:
            wb.close()
        jiufang = client.post(
            "/api/invoice-export/export",
            data={"forwarder_id": "jiufang", "reference_id": "R", "warehouse": "TST1", "order_no": "LCLX"},
            files={"csv_file": ("ship.csv", raw, "text/csv")},
        )
        assert jiufang.status_code == 200, jiufang.text[:400]
        book = _book(jiufang.content)
        try:
            assert book["Invoice"]["U25"].value == asin
        finally:
            book.close()
        stored = get_product_by_sku(sku) or {}
        assert not str(stored.get("asin") or "").strip()
    finally:
        delete_product_by_sku(sku)


def _dim_csv() -> bytes:
    return "\n".join([
        '"货件编号","FBA13DIM1"',
        '"货件名称","B13-DIM"',
        '"配送地址","STEP45VILLE, ZZ"',
        '"箱子数量","1"',
        "",
        '"单件商品（1 箱）"',
        '"SKU","商品名称","ASIN","FNSKU","状况","预处理类型","商品总数","箱子 1 的商品数量"',
        '"B13-DIM","rod","B0B13DIM1","X00TESTDIM","新品","无","4","4"',
        "",
        '"","","","","","","箱号","FBA13DIM1U000001"',
        '"","","","","","","包装箱重量（磅）：","10"',
        '"","","","","","","包装箱长度（英寸）：","17.72"',
        '"","","","","","","包装箱宽度（英寸）：","17.72"',
        '"","","","","","","包装箱高度（英寸）：","16.14"',
    ]).encode("utf-8")


def test_send_dimension_text_uses_two_decimals():
    import re

    from fastapi.testclient import TestClient

    from fba_tool.master_db import delete_product_by_sku
    from main import app

    sku = "B13-DIM"
    delete_product_by_sku(sku)
    _seed(sku, "X00TESTDIM", "B0B13DIM1", "型号乙")
    client = TestClient(app)
    try:
        exported = client.post(
            "/api/invoice-export/export",
            data={"forwarder_id": "send"},
            files={"csv_file": ("dim.csv", _dim_csv(), "text/csv")},
        )
        assert exported.status_code == 200, exported.text[:400]
        wb = _book(exported.content)
        try:
            sheet = next(ws for ws in wb.worksheets if "Invoice" in ws.title)
            text = str(sheet["B15"].value)
        finally:
            wb.close()
    finally:
        delete_product_by_sku(sku)
    assert text == "45.01*45.01*41.00"
    assert re.fullmatch(r"\d+\.\d{2}(\*\d+\.\d{2}){2}", text)


def _lines_csv(count: int) -> bytes:
    headers = ["SKU", "商品名称", "ASIN", "FNSKU", "状况", "预处理类型", "商品总数"]
    headers += [f"箱子 {i} 的商品数量" for i in range(1, count + 1)]
    body = [",".join(f'"{cell}"' for cell in headers)]
    for index in range(1, count + 1):
        qty = ["4" if col == index else "" for col in range(1, count + 1)]
        row = [f"B13-L{index}", "rod", f"B0LINE{index:02d}", f"X00TESTL{index}", "新品", "无", "4", *qty]
        body.append(",".join(f'"{cell}"' for cell in row))
    marks = ["", "", "", "", "", "", "箱号"] + [f"FBA13LINEU{index:06d}" for index in range(1, count + 1)]
    weight = ["", "", "", "", "", "", "包装箱重量（磅）："] + ["10"] * count
    length = ["", "", "", "", "", "", "包装箱长度（英寸）："] + ["10"] * count
    width = ["", "", "", "", "", "", "包装箱宽度（英寸）："] + ["10"] * count
    height = ["", "", "", "", "", "", "包装箱高度（英寸）："] + ["10"] * count
    return "\n".join([
        '"货件编号","FBA13LINE"',
        '"货件名称","B13-LINE"',
        '"配送地址","STEP45VILLE, ZZ"',
        f'"箱子数量","{count}"',
        "",
        f'"多件商品（{count} 箱）"' if count > 1 else '"单件商品（1 箱）"',
        *body,
        "",
        ",".join(f'"{cell}"' for cell in marks),
        ",".join(f'"{cell}"' for cell in weight),
        ",".join(f'"{cell}"' for cell in length),
        ",".join(f'"{cell}"' for cell in width),
        ",".join(f'"{cell}"' for cell in height),
    ]).encode("utf-8")


def _poison_jiufang(raw: bytes) -> bytes:
    wb = _book(raw)
    inv = wb["Invoice"]
    for ref in ("M26:N26", "M27:N27"):
        if ref not in {str(merged) for merged in inv.merged_cells.ranges}:
            inv.merge_cells(ref)
    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    return buf.getvalue()


def _body_mn(ws) -> list[str]:
    return sorted(
        str(merged)
        for merged in ws.merged_cells.ranges
        if merged.min_col == 13 and merged.max_col == 14 and merged.min_row >= 25
    )


def _english_name_csv(title: str) -> bytes:
    return "\n".join([
        '"货件编号","FBAENNAME"',
        '"货件名称","PLAIN"',
        '"配送地址","STEP45VILLE, ZZ"',
        '"箱子数量","1"',
        "",
        '"单件商品（1 箱）"',
        '"SKU","商品名称","ASIN","FNSKU","状况","预处理类型","商品总数","箱子 1 的商品数量"',
        f'"B5-EN","{title}","B0B5ENNAME","X00TESTEN1","新品","无","4","4"',
        "",
        '"","","","","","","箱号","FBAENNAMEU000001"',
        '"","","","","","","包装箱重量（磅）：","10"',
        '"","","","","","","包装箱长度（英寸）：","10"',
        '"","","","","","","包装箱宽度（英寸）：","10"',
        '"","","","","","","包装箱高度（英寸）：","10"',
    ]).encode("utf-8")


def test_qiluo_and_send_english_name_prefer_catalog():
    """qiluo 与 SEND 都用产品库英文名。库里没有时才用货件标题，并且不写回产品库。"""
    from fastapi.testclient import TestClient

    from fba_tool.master_db import delete_product_by_sku, get_product_by_sku, upsert_product
    from main import app

    sku = "B5-EN"
    title = "Lingxing Listing Title"
    catalog = "Catalog Rod"
    delete_product_by_sku(sku)
    _seed(sku, "X00TESTEN1", "B0B5ENNAME", "型号乙", english_name=catalog)
    raw = _english_name_csv(title)
    client = TestClient(app)

    def qiluo_english() -> str:
        generated = client.post(
            "/api/invoice/generate",
            json={
                "shipment_id": "FBAENNAME",
                "forwarder_id": "qiluo",
                "csv_base64": base64.b64encode(raw).decode(),
            },
        )
        assert generated.status_code == 200, generated.text[:400]
        cells = generated.json()["cells"]
        named = [item.get("value") for item in cells if item.get("field_key") == "english_name"]
        assert named, cells
        return str(named[0])

    def send_english() -> str:
        exported = client.post(
            "/api/invoice-export/export",
            data={"forwarder_id": "send"},
            files={"csv_file": ("en.csv", raw, "text/csv")},
        )
        assert exported.status_code == 200, exported.text[:400]
        book = _book(exported.content)
        try:
            sheet = next(ws for ws in book.worksheets if "Invoice" in ws.title)
            return str(sheet["G15"].value)
        finally:
            book.close()

    try:
        assert qiluo_english() == catalog
        assert send_english() == catalog
        stored = get_product_by_sku(sku) or {}
        assert stored.get("english_name") == catalog

        upsert_product({"sku": sku, "english_name": ""}, overwrite=True)
        assert not str((get_product_by_sku(sku) or {}).get("english_name") or "").strip()
        assert qiluo_english() == title
        assert send_english() == title
        assert not str((get_product_by_sku(sku) or {}).get("english_name") or "").strip()
    finally:
        delete_product_by_sku(sku)


def _insert_warehouse(code: str):
    from fba_tool.master_db import _connect

    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute("DELETE FROM fba_warehouse WHERE code = ?", (code,))
        conn.execute(
            """
            INSERT INTO fba_warehouse
                (code, name, company, address1, city, state, zip, country, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (code, code, "Amazon", "1 Test Road", "STEP45VILLE", "ZZ", "00000", "US", now),
        )
        conn.commit()


def test_generate_multi_warehouse_422_names_candidates_in_chinese():
    """同城多仓时生成接口返回可选仓库，文案是中文，指定仓库后不再 422。"""
    from fastapi.testclient import TestClient

    from fba_tool.master_db import _connect, delete_product_by_sku
    from main import app

    sku = "B4-WH"
    _seed(sku, "X00TESTB4W", "B0B4WH0001", "型号乙")
    _insert_warehouse("TST2")
    raw = _csv("FBAB4WH", sku, "X00TESTB4W", "B0B4WH0001").decode("utf-8").replace(
        '"货件名称","B13-DESENS"',
        '"货件名称","PLAIN"',
    ).encode("utf-8")
    client = TestClient(app)
    try:
        generated = client.post(
            "/api/invoice/generate",
            json={
                "shipment_id": "FBAB4WH",
                "forwarder_id": "jiufang",
                "csv_base64": base64.b64encode(raw).decode(),
            },
        )
        assert generated.status_code == 422, generated.text[:500]
        assert "Unprocessable" not in generated.text
        detail = generated.json()["detail"]
        assert detail["code"] == "warehouse_undecided"
        assert "选择仓库" in detail["message"]
        assert "TST1" in detail["warehouse_candidates"]
        assert "TST2" in detail["warehouse_candidates"]

        chosen = client.post(
            "/api/invoice/generate",
            json={
                "shipment_id": "FBAB4WH",
                "forwarder_id": "jiufang",
                "warehouse": "TST2",
                "csv_base64": base64.b64encode(raw).decode(),
            },
        )
        assert chosen.status_code != 422, chosen.text[:500]
        assert chosen.status_code == 200, chosen.text[:500]
    finally:
        delete_product_by_sku(sku)
        with _connect() as conn:
            conn.execute("DELETE FROM fba_warehouse WHERE code = ?", ("TST2",))
            conn.commit()


def test_jiufang_total_merge_follows_the_total_row(monkeypatch):
    from openpyxl.cell.cell import MergedCell

    from fba_tool.invoice_export import _template_bytes, export_invoice, get_export_forwarder
    from fba_tool.shipment_parser import parse_csv_shipment

    fw = get_export_forwarder("jiufang")
    poisoned = _poison_jiufang(_template_bytes(fw))
    header_before = _book(poisoned)["Invoice"]
    kept = sorted(
        str(merged)
        for merged in header_before.merged_cells.ranges
        if merged.min_row < 25
    )
    header_before.parent.close()
    monkeypatch.setattr("fba_tool.invoice_export._template_bytes", lambda _fw: poisoned)

    def products(count: int) -> dict:
        out = {}
        for index in range(1, count + 1):
            fnsku = f"X00TESTL{index}"
            out[fnsku] = {
                "sku": f"B13-L{index}",
                "fnsku": fnsku,
                "asin": f"B0LINE{index:02d}",
                "listing_price": 10.0,
                "english_name": "Item",
                "chinese_name": "物品",
                "brand": "B",
                "material": "铁",
                "purpose": "用",
                "hs_code": "7326909000",
                "model_name": "无",
                "invoice": {
                    "unit": "个",
                    "purchase_price": 5,
                    "material_en": "iron",
                    "purpose_en": "use",
                    "pcs_per_set": 1,
                },
            }
        return out

    warehouse = {"address1": "1 Test Road", "city": "STEP45VILLE", "state": "ZZ", "zip": "00000"}
    expected = {1: ["M26:N26"], 2: ["M27:N27"], 3: ["M28:N28"]}
    for count, merges in expected.items():
        ship = parse_csv_shipment(_lines_csv(count), file_name="lines.csv")
        result = export_invoice(
            "jiufang",
            shipment=ship,
            products=products(count),
            reference_id="R",
            warehouse="TST1",
            warehouse_info=warehouse,
            order_no="LCLX",
        )
        wb = _book(result["bytes"])
        try:
            inv = wb["Invoice"]
            assert _body_mn(inv) == merges
            assert "M27:N27" not in _body_mn(inv) or count == 2
            data_row = 24 + count
            assert not isinstance(inv[f"N{data_row}"], MergedCell)
            assert str(inv[f"N{data_row}"].value) == "7326909000"
            header_now = sorted(str(merged) for merged in inv.merged_cells.ranges if merged.min_row < 25)
            assert header_now == kept
        finally:
            wb.close()
