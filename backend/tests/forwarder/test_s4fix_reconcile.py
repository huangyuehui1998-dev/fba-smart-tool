"""S4-fix1：核对只提建议（确认后生效）、多口径不自动采用、仓库取 CSV 配送地址、无 CSV 标“未核对”、
T5/T7 同分不自动选、坏 JSON 配置、S1–S3 回归、真实 app_data 不被改动。"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from fba_tool import invoice_templates as it

from tests._realdata import skip_module_if_missing

HERE = Path(__file__).resolve().parents[2]
G = HERE / "tests" / "golden"
S = G / "samples"
LEG = S / "invoice_legacy"
INP = S / "inputs"
T7_BLANK = S / "invoice_templates" / "T7_义乌宁波运单下单模板_空白.xlsx"
T5_FILE = LEG / "J-US-第五批9810第一票美国海运ORF2-35箱-PetCarMat发票.xlsx"
B6T5 = LEG / "J-US-第6批9810第5票美国海运MGE3-6箱-PETBARRIERS发票.xlsx"
skip_module_if_missing(HERE / "tests/fixtures/warehouse/fba_warehouse_qiluo.xlsx", T5_FILE, T7_BLANK, B6T5)


def _wh():
    from fba_tool.warehouse_db import parse_warehouse_sheet

    rows, _ = parse_warehouse_sheet((HERE / "tests/fixtures/warehouse/fba_warehouse_qiluo.xlsx").read_bytes(), "q.xlsx")
    return rows


WH = _wh()


# ---------------------------------------------------------------- 第 5 点：T5/T7 同分（S8 D3 起：有数据=T5，空白=T7，自动定）
def test_T5_and_T7_tie_resolved_by_data():
    d = it.detect_template(T5_FILE.read_bytes(), T5_FILE.name)
    assert d["template_id"] == "T5" and d["ambiguous"] is False and set(d["tied"]) == {"T5", "T7"}
    assert it.parse_invoice_file(T5_FILE.read_bytes(), T5_FILE.name)["template_id"] == "T5"   # 不选模板也能解析
    d = it.detect_template(T7_BLANK.read_bytes(), T7_BLANK.name)
    assert d["template_id"] == "T7" and "空白" in d["message"]
    # 手选仍可用
    assert it.parse_invoice_file(T5_FILE.read_bytes(), T5_FILE.name, template_id="T5")["template_id"] == "T5"
    assert it.parse_invoice_file(T7_BLANK.read_bytes(), T7_BLANK.name, template_id="T7")["tickets"] == []


# ---------------------------------------------------------------- 第 4 点：核对
def test_no_csv_means_unverified():
    r = it.parse_invoice_file(B6T5.read_bytes(), B6T5.name)
    assert r["tickets"][0]["verify_status"] == "未核对"
    r2 = it.reconcile_with_csv(r, [])
    t = r2["tickets"][0]
    assert t["verify_status"] == "未核对" and "csv_missing" in {i["code"] for i in t["issues"]}


def test_warehouse_from_csv_ship_to_not_shipment_name():
    from fba_tool.shipment_parser import parse_csv_shipment

    csv = (INP / "第6批-FBA19GDJR25Y.csv").read_bytes()
    s = parse_csv_shipment(csv)
    assert s.ship_to == "Jefferson, GA"
    assert it._ship_to_codes(s.ship_to, WH) == ["MGE3"]
    # 表内写 ACY2（按 sheet 取）：CSV 配送地址对应 MGE3 → 只提建议，确认后才改
    r = it.parse_invoice_file(B6T5.read_bytes(), B6T5.name, overrides={"warehouse_prefer": "sheet"})
    r2 = it.reconcile_with_csv(r, [csv], warehouses=WH)
    t = r2["tickets"][0]
    assert t["warehouse"] == "ACY2" and t["verify_status"] == "待确认"
    p = [x for x in r2["proposals"] if x["field"] == "warehouse"]
    assert [x["proposed"] for x in p] == ["MGE3"]
    r3 = it.apply_corrections(r2, [p[0]["id"]])
    assert r3["tickets"][0]["warehouse"] == "MGE3"
    # 货件名称里的仓库不参与：把货件名称改成别的仓库，结论不变
    fake = csv.decode("utf-8-sig").replace(s.shipment_id, s.shipment_id, 1)
    import re
    fake = re.sub(r'("货件名称",")[^"]*"', r'\1US-6TH-PETBARRIERS-ACY2"', fake)
    r4 = it.reconcile_with_csv(r, [fake.encode("utf-8")], warehouses=WH)
    assert [x["proposed"] for x in r4["proposals"] if x["field"] == "warehouse"] == ["MGE3"]


def test_warehouse_without_address_db_is_unverified_not_changed():
    r = it.parse_invoice_file(B6T5.read_bytes(), B6T5.name, overrides={"warehouse_prefer": "sheet"})
    t = it.reconcile_with_csv(r, [(INP / "第6批-FBA19GDJR25Y.csv").read_bytes()], warehouses=[])["tickets"][0]
    assert t["warehouse"] == "ACY2" and "warehouse_unverified" in {i["code"] for i in t["issues"]} and t["verify_status"] == "待确认"


def _fake_ticket(lines, weight_meaning, qty_meaning="per_box", warehouse="LAX9"):
    tk = {"template_id": "T6", "forwarder": "琪珞", "shipment_id": "FBA1FAKE0001", "warehouse": warehouse, "order_no": "",
          "box_count": max(b for l in lines for b in l["_boxes"]), "gross_kg": None, "qty_meaning": qty_meaning,
          "weight_meaning": weight_meaning, "lines": lines, "issues": []}
    return it._finish(tk)


def _line(boxes, qty, w):
    return {"sku": "A", "chinese_name": "物", "unit_price": 1.0, "_qty_raw": Decimal(str(qty)), "_boxes": boxes, "_weight": Decimal(str(w))}


def _fake_csv(n_boxes, total_qty, weights, ship_to="FONTANA, CA"):
    return SimpleNamespace(ship_to=ship_to, box_count=n_boxes,
                           box_items=pd.DataFrame({"数量": [total_qty]}),
                           box_specs=pd.DataFrame({"实重(kg)": weights}))


def test_multiple_meanings_fit_with_different_results_not_adopted():
    """50 箱每箱 1 件 10kg + 1 箱 2 件：单箱重口径 505kg、单件重口径 510kg，CSV 507kg 两个都在 2% 内 → 不采用任何一个。"""
    tk = _fake_ticket([_line(list(range(1, 51)), 1, 10), _line([51], 2, 5)], None)
    it._reconcile_one(tk, _fake_csv(51, 52, [507 / 51] * 51), WH)
    assert tk["weight_meaning"] is None
    amb = [i for i in tk["issues"] if i["code"] == "weight_meaning_ambiguous"]
    assert amb and set(amb[0]["options"]) == {"per_box", "per_unit"}
    assert {p["proposed"] for p in tk["proposals"] if p["field"] == "weight_meaning"} == {"per_box", "per_unit"}
    # 配了口径也一样：保持配置，但列出另一个并要求确认
    tk2 = _fake_ticket([_line(list(range(1, 51)), 1, 10), _line([51], 2, 5)], "per_box")
    it._reconcile_one(tk2, _fake_csv(51, 52, [507 / 51] * 51), WH)
    assert tk2["weight_meaning"] == "per_box" and [p["proposed"] for p in tk2["proposals"] if p["field"] == "weight_meaning"] == ["per_unit"]


def test_meanings_with_identical_results_are_not_ambiguous():
    """每箱 1 件时单箱重=单件重，结果完全相同：不算歧义，按 CSV 判定。"""
    tk = _fake_ticket([_line([1, 2, 3], 1, 10)], None)
    it._reconcile_one(tk, _fake_csv(3, 3, [10, 10, 10]), WH)
    assert tk["weight_meaning"] in ("per_box", "per_unit") and not [i for i in tk["issues"] if i["code"].endswith("_ambiguous")]


def test_every_correction_is_listed_and_only_applied_after_confirmation():
    """第 9 批（T3）：箱重口径建议 per_unit；不确认 → 原样；确认 → 生效；同组选两个 / 不存在的 id → 报错。"""
    p = S / "invoice_templates" / "T3_第9批第1票_FBA19GQXZW0N.xlsx"
    r = it.reconcile_with_csv(it.parse_invoice_file(p.read_bytes(), p.name), [(INP / "第9批-FBA19GQXZW0N.csv").read_bytes()], warehouses=WH)
    assert r["proposals"] and all({"id", "group", "field", "current", "proposed", "message"} <= set(x) for x in r["proposals"])
    t = r["tickets"][0]
    assert t["weight_meaning"] == "per_box" and t["verify_status"] == "待确认"
    with pytest.raises(ValueError, match="没有这条修正"):
        it.apply_corrections(r, ["nope"])
    pid = [x["id"] for x in r["proposals"] if x["field"] == "weight_meaning"][0]
    with pytest.raises(ValueError, match="同一项只能选一个"):
        it.apply_corrections(r, [pid, pid.replace("per_unit", "range_total")]) if False else it.apply_corrections(
            {**r, "_raw": [{**r["_raw"][0], "proposals": r["_raw"][0]["proposals"] + [{**r["proposals"][0], "id": "x2"}]}]}, [pid, "x2"])
    r2 = it.apply_corrections(r, [pid])
    assert r2["tickets"][0]["weight_meaning"] == "per_unit" and not [x for x in r2["proposals"] if x["field"] == "weight_meaning"]


def test_box_count_correction_is_a_proposal():
    """T6 第 6 批配置成 box_count_source=range 时，箱号区间 1–30 ≠ CSV 6 箱 → 提建议，不自己改。"""
    p = LEG / "J-US-第6批9810第1票美国海运ILG1-6箱-PETBARRIERS发票.xlsx"
    r = it.parse_invoice_file(p.read_bytes(), p.name, overrides={"box_count_source": "range"})
    r2 = it.reconcile_with_csv(r, [(INP / "第6批-FBA19GDLZ88C.csv").read_bytes()], warehouses=WH)
    t = r2["tickets"][0]
    assert t["box_count"] == 30
    bc = [x for x in r2["proposals"] if x["field"] == "box_count"]
    assert [x["proposed"] for x in bc] == [6]
    t3 = it.apply_corrections(r2, [bc[0]["id"]])["tickets"][0]
    assert t3["box_count"] == 6


def test_api_parse_preview_then_accept():
    from fastapi.testclient import TestClient

    from main import app

    c = TestClient(app)
    p = S / "invoice_templates" / "T3_第9批第1票_FBA19GQXZW0N.xlsx"
    csv = (INP / "第9批-FBA19GQXZW0N.csv").read_bytes()
    r = c.post("/api/invoice-templates/parse", files=[("file", (p.name, p.read_bytes())), ("csv_files", ("a.csv", csv))])
    assert r.status_code == 200
    j = r.json()
    pid = [x["id"] for x in j["proposals"] if x["field"] == "weight_meaning"][0]
    assert j["tickets"][0]["weight_meaning"] == "per_box"
    r = c.post("/api/invoice-templates/parse", files=[("file", (p.name, p.read_bytes())), ("csv_files", ("a.csv", csv))],
               data={"accept": json.dumps([pid])})
    assert r.status_code == 200 and r.json()["tickets"][0]["weight_meaning"] == "per_unit"
    r = c.post("/api/invoice-templates/parse", files=[("file", (p.name, p.read_bytes()))], data={"accept": json.dumps([pid])})
    assert r.status_code == 422


# ---------------------------------------------------------------- D-09 第 2 点：全部琪珞 T6 样例
@pytest.mark.parametrize("name,csv,meaning", [
    ("J-US-第6批9810第1票美国海运ILG1-6箱-PETBARRIERS发票.xlsx", "第6批-FBA19GDLZ88C.csv", "per_unit"),
    ("J-US-第6批9810第2票美国海运SMF6-6箱-PETBARRIERS发票.xlsx", "第6批-FBA19GDN35JP.csv", "per_unit"),
    ("J-US-第6批9810第3票美国海运JAX3-6箱-PETBARRIERS发票.xlsx", "第6批-FBA19GDPP6M8.csv", "per_unit"),
    ("J-US-第6批9810第4票美国海运ACY2-6箱-PETBARRIERS发票.xlsx", "第6批-FBA19GDL9K3X.csv", "per_unit"),
    ("J-US-第6批9810第5票美国海运MGE3-6箱-PETBARRIERS发票.xlsx", "第6批-FBA19GDJR25Y.csv", "per_unit"),
])
def test_d09_point2_batch6_single_piece_weight_decided_by_csv(name, csv, meaning):
    p = LEG / name
    r = it.parse_invoice_file(p.read_bytes(), p.name)
    assert r["tickets"][0]["weight_meaning"] is None  # 不默认
    t = it.reconcile_with_csv(r, [(INP / csv).read_bytes()], warehouses=WH)["tickets"][0]
    assert t["weight_meaning"] == meaning and t["boxes"] == [20.0] * 6


def test_d09_point2_batch7_is_per_box():
    p = S / "invoice_templates" / "T6_第7批第1票_VGT2-29箱.xlsx"
    t = it.reconcile_with_csv(it.parse_invoice_file(p.read_bytes(), p.name), [(INP / "第7批-FBA19GVFX5SC.csv").read_bytes()], warehouses=WH)["tickets"][0]
    assert t["weight_meaning"] == "per_box" and round(sum(t["boxes"]), 2) == 168.23


def test_t6_config_has_no_default_weight_meaning():
    raw = json.loads((HERE / "config" / "invoice_template_map.json").read_text(encoding="utf-8"))
    assert raw["templates"]["T6"]["weight_meaning"] is None


# ---------------------------------------------------------------- 坏 JSON 配置
def test_bad_json_user_config_gives_clear_error(monkeypatch, tmp_path):
    bad = tmp_path / "invoice_template_map.json"
    bad.write_text('{"templates": {"T6": {"weight_meaning": "per_box",}}', encoding="utf-8")
    monkeypatch.setattr(it, "_user_config_path", lambda: bad)
    with pytest.raises(ValueError, match="配置文件格式错误.*第 1 行"):
        it.list_templates()
    from fastapi.testclient import TestClient

    from main import app

    c = TestClient(app)
    r = c.post("/api/invoice-templates/detect", files={"file": (B6T5.name, B6T5.read_bytes())})
    assert r.status_code == 422 and "配置文件格式错误" in r.json()["detail"]
    bad.write_text('["not", "an", "object"]', encoding="utf-8")
    with pytest.raises(ValueError, match="顶层应是 JSON 对象"):
        it.list_templates()
    bad.write_text('{"templates": ["T6"]}', encoding="utf-8")
    with pytest.raises(ValueError, match="templates 应是对象"):
        it.list_templates()


def test_get_templates_api_bad_json_is_422(monkeypatch, tmp_path):
    bad = tmp_path / "invoice_template_map.json"
    bad.write_text("{", encoding="utf-8")
    monkeypatch.setattr(it, "_user_config_path", lambda: bad)
    from fastapi.testclient import TestClient

    from main import app

    r = TestClient(app).get("/api/invoice-templates")
    assert r.status_code == 422


# ---------------------------------------------------------------- S1–S3 回归
def test_s1_csv_warehouse_still_from_shipment_name_for_packing_flow():
    """S1 的装箱/箱唛流程仍按货件名称取仓库（这里只给发票核对加了 ship_to，不改原字段）。"""
    import re

    from fba_tool.shipment_parser import parse_csv_shipment

    n = 0
    for f in sorted(INP.glob("*.csv")):
        text = f.read_bytes().decode("utf-8-sig")
        name = re.search(r'"货件名称","([^"]*)"', text).group(1)
        s = parse_csv_shipment(f.read_bytes(), file_name=f.name)
        codes = re.findall(r"(?<![A-Z0-9])([A-Z]{3}\d)(?![A-Z0-9])", name.upper())
        if codes:
            assert s.warehouse_code == codes[-1] and s.warehouse_source == "货件名称", f.name
            n += 1
        assert s.ship_to and "," in s.ship_to
    assert n >= 15


def test_s2_declared_price_order_unchanged():
    from fba_tool.product_fields import resolve_declared_price

    assert resolve_declared_price({"listing_price": 9.9, "declared_value": 5, "field_sources": {"declared_value": "manual"}}) == (9.9, "lingxing")
    assert resolve_declared_price({"declared_value": 5, "field_sources": {"declared_value": "manual"}}) == (5.0, "manual")
    assert resolve_declared_price({"listing_price": 8.0, "listing_price_basis": "price"}) == (8.0, "lingxing_price")
    assert resolve_declared_price({"declared_value": 5}) == (5.0, "legacy")
    assert resolve_declared_price({}) == (None, "")


def test_s3_invoice_parse_feeds_customs_golden_input_JUS6HB30():
    """发票解析 → CSV 判定口径 → 报关票输入，与 S3 报关 golden 的 JUS6HB30 输入逐票一致（箱重、件数、单价）。"""
    inputs = json.loads((G / "customs_inputs.json").read_text(encoding="utf-8"))["JUS6HB30"]["tickets"]
    by = {t["shipment_id"]: t for t in inputs}
    csvs = [c.read_bytes() for c in INP.glob("第6批-*.csv")]
    for p in sorted(LEG.glob("*第6批*")):
        r = it.reconcile_with_csv(it.parse_invoice_file(p.read_bytes(), p.name), csvs, warehouses=WH)
        c = it.to_customs_ticket(r["tickets"][0])
        exp = by[c["shipment_id"]]
        assert c["boxes"] == exp["boxes"] and c["warehouse"] == exp["warehouse"]
        assert [(l["qty"], l["unit_price"]) for l in c["lines"]] == [(float(l["qty"]), l["unit_price"]) for l in exp["lines"]]


def test_s3_customs_golden_still_zero_failures(monkeypatch, tmp_path):
    import test_golden_customs as tg

    ad = tmp_path / "ad"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    from fba_tool.master_db import init_master_db

    init_master_db()
    monkeypatch.setattr(tg.cp, "_catalog_hints", lambda sku: {})
    rows = []
    for cid in sorted(tg.MANIFEST):
        rows += tg.run_case(cid, "xlsx", tmp_path)
    assert not tg.cg.failures(rows)


# ---------------------------------------------------------------- 真实 app_data 不被改动
def _tree_hash(root: Path):
    out = {}
    if root.exists():
        for f in sorted(root.rglob("*")):
            if f.is_file():
                out[str(f.relative_to(root))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def test_real_app_data_unchanged_by_s4_flows(tmp_path):
    from fastapi.testclient import TestClient

    from fba_tool.app_paths import app_data_dir
    from main import app
    import test_s4fix_invoice_export as tx

    real = HERE.parent / "app_data"
    assert Path(app_data_dir()).resolve() != real.resolve()  # conftest 已把 app_data 指到临时目录
    before = _tree_hash(real)
    # 解析 + 核对 + 确认 + 导出（SEND / 九方）+ API
    p = S / "invoice_templates" / "T3_第9批第1票_FBA19GQXZW0N.xlsx"
    r = it.reconcile_with_csv(it.parse_invoice_file(p.read_bytes(), p.name), [(INP / "第9批-FBA19GQXZW0N.csv").read_bytes()])
    it.apply_corrections(r, [r["proposals"][0]["id"]])
    for case in tx.INPUTS[:1] + tx.INPUTS[5:6]:
        tx._export(case)
    c = TestClient(app)
    c.get("/api/invoice-templates")
    c.post("/api/invoice-templates/detect", files={"file": (p.name, p.read_bytes())})
    c.get("/api/invoice-export/forwarders")
    after = _tree_hash(real)
    assert before == after


# ---------------------------------------------------------------- S4-final：VGT2 地址纠错（D-06，出处见 config/fba_warehouse_corrections.json）
def test_vgt2_address_corrected_with_source():
    from fba_tool.warehouse_db import load_corrections

    vgt2 = next(r for r in WH if r["code"] == "VGT2")
    assert (vgt2["address1"], vgt2["city"], vgt2["state"], vgt2["zip"]) == ("6401 Howdy Wells Avenue", "Las Vegas", "NV", "89115")
    c = load_corrections()["VGT2"]
    assert "sellercentral.amazon.com" in c["source"] and "March Air Reserve Base" in c["was"]
    # 其它仓库不受影响
    assert next(r for r in WH if r["code"] == "LAX9")["address1"] == "11263 Oleander Ave"


def test_vgt2_corrected_in_db_read_path_and_import_preview():
    from fba_tool.master_db import init_master_db
    from fba_tool.warehouse_db import apply_warehouse_import, get_warehouse, parse_warehouse_sheet

    init_master_db()
    data = (HERE / "tests/fixtures/warehouse/fba_warehouse_qiluo.xlsx").read_bytes()
    _, issues = parse_warehouse_sheet(data, "q.xlsx")
    assert any("VGT2" in i["message"] and "纠正" in i["message"] for i in issues)
    apply_warehouse_import(data, "q.xlsx")
    w = get_warehouse("VGT2")
    assert w["city"] == "Las Vegas" and w["state"] == "NV"


def test_batch7_vgt2_ticket_now_verified_by_ship_to():
    p = S / "invoice_templates" / "T6_第7批第1票_VGT2-29箱.xlsx"
    t = it.reconcile_with_csv(it.parse_invoice_file(p.read_bytes(), p.name), [(INP / "第7批-FBA19GVFX5SC.csv").read_bytes()], warehouses=WH)["tickets"][0]
    assert t["warehouse"] == "VGT2"
    assert not [i for i in t["issues"] if i["code"] in ("warehouse_ambiguous", "warehouse_unverified")]
    assert any(d["field"] == "warehouse" for d in t["decisions"])
