"""代码方 r2：第 14 批包装箱名称、填写失败禁导出、分步进度、V4、端口 8010。"""
from __future__ import annotations

import csv
import io
import re
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
FORWARDERS = ("send", "jiufang", "qiluo", "qiluo_t5", "qiluo_t6", "deshu")


def _sta_batch14_csv() -> bytes:
    """第 14 批 Send to Amazon 的形状：6 个 SKU，箱号行是「包装箱名称 / P1 - Bn」，没有「箱号」或 FBA…U。"""
    rows: list[list[object]] = [
        ["货件编号", "FBATEST14B"],
        ["货件名称", "BATCH14-TST1"],
        ["配送地址", "STEP45VILLE, ZZ"],
        ["箱子数量", "2"],
        [],
        ["SKU", "商品名称", "ASIN", "FNSKU", "状况", "预处理类型", "商品预处理方是谁？", "商品贴标方是谁？", "预计数量", "装箱数量", "", "包装箱 1 数量", "包装箱 2 数量"],
    ]
    for index in range(1, 7):
        rows.append([
            f"STA14-SKU-{index}",
            "item",
            f"B0STA14{index:02d}",
            f"X00TEST14{index}",
            "NewItem",
            "贴标",
            "",
            "由卖家提供",
            4,
            4,
            "",
            4 if index <= 3 else "",
            2 if index > 3 else "",
        ])
    rows.append([])

    def foot(label: str, left: object, right: object) -> list[object]:
        return [label, *( [""] * 10 ), left, right]

    rows.extend([
        foot("包装箱名称", "P1 - B1", "P1 - B2"),
        foot("包装箱重量（磅）：", "10", "11"),
        foot("包装箱宽度（英寸）：", "17.70", "10"),
        foot("包装箱长度（英寸）：", "17.70", "12"),
        foot("包装箱高度（英寸）：", "16.10", "8"),
    ])
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode("utf-8")


def _seed_sta():
    import json
    from datetime import datetime, timezone

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
    for index in range(1, 7):
        sku = f"STA14-SKU-{index}"
        upsert_product(
            {
                "sku": sku,
                "fnsku": f"X00TEST14{index}",
                "asin": f"B0STA14{index:02d}",
                "english_name": "Fishing rod",
                "chinese_name": "鱼竿",
                "brand": "Acme",
                "material": "棉",
                "purpose": "宠物",
                "hs_code": "9507100090",
                "model_name": "型号甲",
                "extra_data": json.dumps(
                    {"invoice": {"unit": "个", "purchase_price": 5, "material_en": "cotton", "purpose_en": "pet", "pcs_per_set": 1}},
                    ensure_ascii=False,
                ),
            }
        )
        set_product_fields(sku, {"listing_price": 12.5, "listing_price_currency": "USD"}, SOURCE_MANUAL)


def test_batch14_packaging_name_row_maps_p1_boxes_and_keeps_inches():
    from fba_tool.shipment_parser import parse_csv_shipment

    ship = parse_csv_shipment(_sta_batch14_csv(), file_name="第14批.csv", allow_unassigned_fba=True)
    assert ship.shipment_id == "FBATEST14B"
    assert ship.column_to_box
    assert set(ship.column_to_box.values()) == {1, 2}
    assert ship.box_count == 2
    assert not ship.box_items.empty
    assert int(ship.box_items["数量"].sum()) == 4 * 3 + 2 * 3
    marks = ship.box_specs["FBA箱号"].fillna("").astype(str).str.strip()
    assert list(marks) == ["", ""]
    assert set(ship.box_specs["箱名"].astype(str)) == {"P1 - B1", "P1 - B2"}
    assert ship.box_names == {1: "P1 - B1", 2: "P1 - B2"}
    assert ship.box_fba_ids == {}
    width = float(ship.box_specs.loc[ship.box_specs["箱号"] == 1, "宽(cm)"].iloc[0])
    length = float(ship.box_specs.loc[ship.box_specs["箱号"] == 1, "长(cm)"].iloc[0])
    assert width == 44.96
    assert length == 44.96


def test_send_quantity_is_sku_total_not_per_box():
    """同一 SKU 的 SEND 数量是各箱数量加总，不是单箱数量。重量差 0.003 kg 仍合并成一行。"""
    import io

    from openpyxl import load_workbook

    from fba_tool.invoice_export import SEND_SHEET, export_invoice
    from fba_tool.invoice_rules import Box, box_ranges, sku_totals
    from fba_tool.shipment_parser import parse_csv_shipment

    per_box = 4
    box_count = 8
    dims = (45.0, 45.0, 41.0)
    near = [
        Box(i, f"FBATEST8QU{i:06d}", [("X00TEST8Q", per_box)], 10.004 if i % 2 else 10.001, dims)
        for i in range(1, box_count + 1)
    ]
    sku_total = sum(qty for _sku, qty in sku_totals(near))
    assert sku_total == per_box * box_count
    assert sku_total != per_box
    assert [(row.label, row.qty) for row in box_ranges(near)] == [(f"1-{box_count}", sku_total)]
    apart = box_ranges([
        Box(1, "", [("A", per_box)], 7.5, dims),
        Box(2, "", [("A", per_box)], 7.6, dims),
    ])
    assert [(row.label, row.weight) for row in apart] == [("1", 7.5), ("2", 7.6)]

    def quoted(cells: list[object]) -> str:
        return ",".join(f'"{cell}"' for cell in cells)

    headers = ["SKU", "商品名称", "ASIN", "FNSKU", "状况", "预处理类型", "商品总数"]
    headers += [f"箱子 {i} 的商品数量" for i in range(1, box_count + 1)]
    line = ["QTY-SKU", "rod", "B0QTY00001", "X00TEST8Q", "新品", "无", str(sku_total), *[str(per_box)] * box_count]
    marks = ["", "", "", "", "", "", "箱号"] + [f"FBATEST8QU{i:06d}" for i in range(1, box_count + 1)]
    weight = ["", "", "", "", "", "", "包装箱重量（kg）："] + ["10"] * box_count
    length = ["", "", "", "", "", "", "包装箱长度（cm）："] + ["40"] * box_count
    width = ["", "", "", "", "", "", "包装箱宽度（cm）："] + ["40"] * box_count
    height = ["", "", "", "", "", "", "包装箱高度（cm）："] + ["40"] * box_count
    raw = "\n".join([
        '"货件编号","FBATEST8Q"',
        '"货件名称","QTY"',
        '"配送地址","STEP45VILLE, ZZ"',
        '"箱子数量","8"',
        "",
        '"单件商品（8 箱）"',
        quoted(headers),
        quoted(line),
        "",
        quoted(marks),
        quoted(weight),
        quoted(length),
        quoted(width),
        quoted(height),
    ]).encode()
    ship = parse_csv_shipment(raw, allow_unassigned_fba=True)
    parsed_total = int(ship.box_items["数量"].sum())
    assert parsed_total == sku_total
    result = export_invoice(
        "send",
        shipment=ship,
        products={
            "X00TEST8Q": {
                "sku": "QTY-SKU",
                "fnsku": "X00TEST8Q",
                "asin": "B0QTY00001",
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
        },
        reference_id="R",
    )
    wb = load_workbook(io.BytesIO(result["bytes"]))
    try:
        ws = wb[SEND_SHEET]
        assert ws["A15"].value == f"1-{box_count}"
        assert ws["F15"].value == parsed_total
        assert ws["F15"].value != per_box
        assert ws["F16"].value in (None, "")
    finally:
        wb.close()


def test_classic_fba_box_row_still_maps():
    from fba_tool.shipment_parser import parse_csv_shipment

    raw = "\n".join([
        '"货件编号","FBATESTBOX1"',
        '"货件名称","BOX-TST1"',
        '"配送地址","STEP45VILLE, ZZ"',
        '"箱子数量","1"',
        "",
        '"SKU","商品名称","ASIN","FNSKU","状况","预处理类型","商品总数","箱子 1 的商品数量"',
        '"BOX-SKU","rod","B0BOX00001","X00TESTBOX","新品","无","4","4"',
        "",
        '"","","","","","","箱号","FBATESTBOX1U000001"',
    ]).encode()
    ship = parse_csv_shipment(raw, allow_unassigned_fba=True)
    assert ship.column_to_box
    assert 1 in ship.column_to_box.values()
    assert ship.box_fba_ids.get(1, "").upper().endswith("U000001")


def test_workflow_fill_defines_rec_with_and_without_catalog():
    from fba_tool.invoice_workflow_fill import build_invoice_line_items_workflow
    from fba_tool.shipment_parser import parse_csv_shipment

    raw = _sta_batch14_csv()
    ship = parse_csv_shipment(raw, allow_unassigned_fba=True)

    class Rec:
        unit_cost = 3.5
        asin = "B0FROMREC"

    class Cat:
        def lookup(self, sku):
            return Rec() if str(sku).startswith("STA14-SKU-") else None

    filled = build_invoice_line_items_workflow(ship, raw, Cat(), None)
    assert filled
    assert all(item.values["purchase_price"] == 3.5 for item in filled)
    bare = build_invoice_line_items_workflow(ship, raw, None, None)
    assert bare
    assert bare[0].values["purchase_price"] == ""
    assert bare[0].values["asin"]


@pytest.mark.parametrize("forwarder_id", FORWARDERS)
def test_sta_shape_autofill_then_export(forwarder_id):
    import base64

    from fastapi.testclient import TestClient

    from main import app

    _seed_sta()
    raw = _sta_batch14_csv()
    client = TestClient(app)
    generated = client.post(
        "/api/invoice/generate",
        json={
            "shipment_id": "FBATEST14B",
            "forwarder_id": forwarder_id,
            "csv_base64": base64.b64encode(raw).decode(),
            "po_number": "PO-14",
        },
    )
    assert generated.status_code == 200, generated.text
    assert "未找到「箱号」" not in generated.text
    assert "is not defined" not in generated.text
    body = generated.json()
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
    assert exported.status_code == 200, exported.text
    assert exported.content[:2] == b"PK"
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(exported.content), data_only=True)
    texts = set()
    for ws in wb.worksheets:
        for row in ws.iter_rows(max_row=min(ws.max_row or 1, 80), max_col=min(ws.max_column or 1, 30)):
            for cell in row:
                if cell.value not in (None, ""):
                    texts.add(str(cell.value).strip())
    wb.close()
    assert "FBATEST14B" in texts


def test_snapshot_progress_steps_before_100():
    import openpyxl

    from fba_tool.univer_snapshot import workbook_to_snapshot

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in range(1, 41):
        for col in range(1, 6):
            ws.cell(row, col, f"{row}-{col}")
    buf = io.BytesIO()
    wb.save(buf)
    seen: list[int] = []
    workbook_to_snapshot(buf.getvalue(), progress=seen.append)
    assert any(0 < value < 100 for value in seen), seen
    assert seen[-1] == 100
    assert seen == sorted(seen)


def test_job_poll_sees_progress_between_0_and_100():
    from fba_tool.job_runner import RUNNER

    started = threading.Event()
    release = threading.Event()

    def fn(job):
        job.progress = 35
        started.set()
        assert release.wait(2)
        job.progress = 75
        return {"ok": True}

    job, _done = RUNNER.submit(fn, sync_timeout=0)
    assert started.wait(2)
    assert RUNNER.get(job.id).progress == 35
    release.set()
    assert job.done.wait(2)
    assert job.status == "done"
    assert job.progress == 100


def test_run_app_candidate_ports_skip_8010():
    text = (ROOT / "run_app.py").read_text(encoding="utf-8")
    match = re.search(r"^PREFERRED_PORTS = (.+)$", text, re.M)
    assert match
    ports = list(eval(match.group(1), {"DEFAULT_PORT": 8002, "range": range}))
    assert ports[0] == 8002
    assert 8003 in ports and 8009 in ports and 8011 in ports and 18002 in ports
    assert 8010 not in ports


def _batch_csvs(root: Path) -> dict[str, list[Path]]:
    found = {"13": [], "14": []}
    for path in root.rglob("*.csv"):
        if path.name.startswith("~$"):
            continue
        text = str(path)
        if "第13批" in text or "/13/" in text.replace("\\", "/"):
            found["13"].append(path)
        elif "第14批" in text or "/14/" in text.replace("\\", "/"):
            found["14"].append(path)
    return found


def _invoice_files(root: Path) -> list[Path]:
    found = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name.startswith("~$"):
            continue
        if path.suffix.lower() not in {".xlsx", ".xlsm"}:
            continue
        name = path.name.lower()
        if any(token in path.name for token in ("发票", "箱单", "Invoice", "invoice")):
            found.append(path)
        elif "send" in name and "amazon" not in name:
            found.append(path)
    return found


def _text_has_qty(texts: set[str], qty: str) -> bool:
    if qty in texts:
        return True
    try:
        number = float(qty)
    except ValueError:
        return False
    for text in texts:
        try:
            if float(text) == number:
                return True
        except ValueError:
            continue
    return False


def _workbook_texts(data: bytes) -> set[str]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    texts: set[str] = set()
    try:
        for ws in wb.worksheets:
            for row in ws.iter_rows(max_row=min(ws.max_row or 1, 120), max_col=min(ws.max_column or 1, 40)):
                for cell in row:
                    if cell.value not in (None, ""):
                        texts.add(str(cell.value).strip())
    finally:
        wb.close()
    return texts


def _catalog_seed(rec, meta: dict) -> dict | None:
    """真实批次种子：ASIN 来自 CSV 的 SKU 行，没有再看装箱行。"""
    import json

    from fba_tool.sku_keys import lookup_sku

    sku_text = str(rec.get("SKU") or "").strip()
    if not sku_text:
        return None
    hit = lookup_sku(meta, sku_text, {}) or {}
    asin = str(hit.get("asin") or "").strip()
    if not asin:
        for key in getattr(rec, "index", []):
            if str(key).strip().upper() == "ASIN":
                asin = str(rec.get(key) or "").strip()
                break
    fnsku = str(rec.get("FNSKU") or hit.get("fnsku") or "").strip().upper()
    return {
        "sku": sku_text,
        "fnsku": fnsku,
        "asin": asin,
        "english_name": "Item",
        "chinese_name": "物品",
        "brand": "Brand",
        "material": "棉",
        "purpose": "宠物",
        "hs_code": "9507100090",
        "model_name": "M",
        "extra_data": json.dumps(
            {"invoice": {"unit": "个", "purchase_price": 5, "material_en": "cotton", "purpose_en": "pet", "pcs_per_set": 1}},
            ensure_ascii=False,
        ),
    }


def test_real_batch_seed_copies_asin_from_csv():
    from fba_tool.invoice_table import extract_csv_sku_meta
    from fba_tool.shipment_parser import parse_csv_shipment

    raw = _sta_batch14_csv()
    ship = parse_csv_shipment(raw, file_name="batch14.csv", allow_unassigned_fba=True)
    meta = extract_csv_sku_meta(raw)
    seeds = []
    for _, rec in ship.box_items.iterrows():
        seed = _catalog_seed(rec, meta)
        if seed:
            seeds.append(seed)
    assert seeds
    assert all(item["asin"].startswith("B0STA14") for item in seeds)
    assert all(item["fnsku"].startswith("X00TEST14") for item in seeds)


def test_real_batches_13_and_14_autofill_export_matches_invoices(monkeypatch, tmp_path):
    """真实目录在时跑六个货代的自动填写→导出，并和同票发票核对货件号与数量。"""
    from tests.smoke.reference import LayoutMissing, available, realdata_root

    if not available():
        pytest.skip("需要 box realdata")
    monkeypatch.setenv("FBA_APP_DATA_DIR", str(tmp_path / "app"))
    monkeypatch.setenv("FBA_DISABLE_SCHEDULER", "1")
    root = realdata_root()
    csvs = _batch_csvs(root)
    missing = [batch for batch, paths in csvs.items() if not paths]
    if missing:
        raise LayoutMissing("缺少第 " + "、".join(missing) + " 批货件 CSV")

    import base64

    from fastapi.testclient import TestClient

    from fba_tool.master_db import init_master_db, upsert_product
    from fba_tool.product_fields import SOURCE_MANUAL, set_product_fields
    from fba_tool.shipment_parser import parse_csv_shipment
    from main import create_app

    init_master_db()
    client = TestClient(create_app())
    invoices = _invoice_files(root)
    compared = []
    pipeline = []
    for batch, paths in csvs.items():
        for path in paths:
            raw = path.read_bytes()
            try:
                ship = parse_csv_shipment(raw, file_name=path.name, allow_unassigned_fba=True)
            except ValueError as exc:
                raise AssertionError(f"{path.name} 解析失败：{exc}") from exc
            if ship.box_items.empty:
                raise AssertionError(f"{path.name} 没有箱内数量")
            from fba_tool.invoice_table import extract_csv_sku_meta

            meta = extract_csv_sku_meta(raw)
            for _, rec in ship.box_items.iterrows():
                seed = _catalog_seed(rec, meta)
                if not seed:
                    continue
                upsert_product(seed)
                set_product_fields(seed["sku"], {"listing_price": 10, "listing_price_currency": "USD"}, SOURCE_MANUAL)
            qty_tokens = {str(int(value)) for value in ship.box_items["数量"] if int(value) > 0}
            # SEND 数量是每个 SKU 的装箱数量之和，从 CSV 算，不写死。评审样本加总后与原发票一致。
            sku_qty: dict[str, int] = {}
            for _, rec in ship.box_items.iterrows():
                sku_name = str(rec.get("SKU") or "")
                sku_qty[sku_name] = sku_qty.get(sku_name, 0) + int(rec["数量"])
            sku_qty_tokens = {str(total) for total in sku_qty.values() if total > 0}
            for forwarder_id in FORWARDERS:
                generated = client.post(
                    "/api/invoice/generate",
                    json={
                        "shipment_id": ship.shipment_id,
                        "forwarder_id": forwarder_id,
                        "csv_base64": base64.b64encode(raw).decode(),
                    },
                )
                assert generated.status_code == 200, f"{batch} {path.name} {forwarder_id} {generated.text}"
                assert "箱号" not in generated.text
                body = generated.json()
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
                assert exported.status_code == 200, f"{batch} {path.name} {forwarder_id} export {exported.text[:300]}"
                texts = _workbook_texts(exported.content)
                assert ship.shipment_id in texts, f"{forwarder_id} 导出没有货件号 {ship.shipment_id}"
                if forwarder_id == "send":
                    missing_totals = {qty for qty in sku_qty_tokens if not _text_has_qty(texts, qty)}
                    assert not missing_totals, (
                        f"send 数量应是 CSV 按 SKU 加总的 {sorted(sku_qty_tokens)}，"
                        f"与原发票一致，不能用单箱数量 {sorted(qty_tokens)} 代替，缺 {sorted(missing_totals)}"
                    )
                else:
                    assert qty_tokens & texts, f"{forwarder_id} 导出没有 CSV 数量 {qty_tokens}"
                pipeline.append((batch, path.name, forwarder_id, ship.shipment_id))
                for invoice in invoices:
                    if ship.shipment_id and ship.shipment_id in invoice.name.upper().replace("-", ""):
                        invoice_texts = _workbook_texts(invoice.read_bytes())
                        assert ship.shipment_id in invoice_texts
                        if forwarder_id == "send":
                            shared = {qty for qty in sku_qty_tokens if _text_has_qty(invoice_texts, qty)}
                            assert shared, (
                                f"{invoice.name} 应包含 CSV 按 SKU 加总的数量 {sorted(sku_qty_tokens)}，"
                                "这就是 SEND 要写出的数量"
                            )
                            missing_in_export = {qty for qty in shared if not _text_has_qty(texts, qty)}
                        else:
                            shared = (qty_tokens & invoice_texts) or ({str(int(ship.box_items["数量"].sum()))} & invoice_texts)
                            assert shared, f"{invoice.name} 和 CSV 数量对不上 {qty_tokens}"
                            missing_in_export = shared - texts
                        assert not missing_in_export, f"{forwarder_id} 导出缺真实发票里的数量 {missing_in_export}"
                        compared.append((forwarder_id, ship.shipment_id, invoice.name))
    assert pipeline
    if invoices and not compared:
        raise AssertionError("找到了发票文件，但没有一份能按货件号和第 13/14 批 CSV 对上：" + ", ".join(path.name for path in invoices[:8]))
