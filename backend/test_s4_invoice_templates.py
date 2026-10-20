"""S4：发票模板映射（8 套模板 T1–T8）——自动识别、手动选择、字段映射、和货件 CSV 交叉核对（D-08 / D-09）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from fba_tool import invoice_templates as it
from tests._realdata import skip_module_if_missing

G = Path(__file__).parent / "tests" / "golden" / "samples"
skip_module_if_missing(G)
T = G / "invoice_templates"
LEG = G / "invoice_legacy"
INV = G / "invoice"
INP = G / "inputs"

SAMPLES = {
    "T1": T / "T1_第10批第1票_FBA19HPYMVDM-MCI4.xlsx",
    "T2": INV / "FBA19P4N6MM2发票.xlsx",
    "T3": T / "T3_第9批第1票_FBA19GQXZW0N.xlsx",
    "T3b": T / "T3_第2批第一票_FBA19CG4R0LP.xlsx",
    "T4": T / "T4_第4批第一票_FWA4-27箱_去图片副本.xlsx",
    "T5": LEG / "J-US-第五批9810第一票美国海运ORF2-35箱-PetCarMat发票.xlsx",
    "T6": T / "T6_第7批第1票_VGT2-29箱.xlsx",
    "T6b6t1": LEG / "J-US-第6批9810第1票美国海运ILG1-6箱-PETBARRIERS发票.xlsx",
    "T6b6t5": LEG / "J-US-第6批9810第5票美国海运MGE3-6箱-PETBARRIERS发票.xlsx",
    "T7": T / "T7_义乌宁波运单下单模板_空白.xlsx",
    "T8": INV / "LCL2607GZ0PA-箱单发票.xlsx",
}


def _parse(key, **kw):
    p = SAMPLES[key]
    return it.parse_invoice_file(p.read_bytes(), p.name, **kw)


def _csv(name):
    return (INP / name).read_bytes()


@pytest.mark.parametrize("key,tid", [("T1", "T1"), ("T2", "T2"), ("T3", "T3"), ("T3b", "T3"), ("T4", "T4"),
                                     ("T6", "T6"), ("T6b6t1", "T6"), ("T8", "T8")])
def test_auto_detect_unique(key, tid):
    p = SAMPLES[key]
    d = it.detect_template(p.read_bytes(), p.name)
    assert d["template_id"] == tid and d["ambiguous"] is False
    assert d["candidates"][0]["template_id"] == tid


def test_all_eight_templates_configured_with_forwarder_and_evidence():
    cfg = {t["id"]: t for t in it.list_templates()}
    assert set(cfg) == {f"T{i}" for i in range(1, 9)}
    assert cfg["T3"]["forwarder"] == "德速" and cfg["T4"]["forwarder"] == "九方" and cfg["T5"]["forwarder"] == "琪珞"
    assert cfg["T6"]["forwarder"] == "琪珞" and cfg["T1"]["forwarder"] == "九方" and cfg["T2"]["forwarder"] == "SEND"
    for t in cfg.values():
        assert t.get("decision")  # 每套都写了依据（D-09 / 盘点）


def test_manual_select_and_wrong_manual_pick():
    r = _parse("T1", template_id="T1")
    assert r["template_id"] == "T1" and r["detected_by"] == "manual"
    with pytest.raises(ValueError, match="T6"):
        _parse("T1", template_id="T6")
    with pytest.raises(ValueError, match="没有这个模板"):
        _parse("T1", template_id="T99")


def _one(r):
    assert len(r["tickets"]) == 1
    return r["tickets"][0]


def test_T1_jiufang_order_form():
    t = _one(_parse("T1"))
    assert (t["shipment_id"], t["warehouse"], t["box_count"]) == ("FBA19HPYMVDM", "MCI4", 33)
    assert t["boxes"][0] == 6.81 and t["boxes"][1] == 6.81 and t["boxes"][4] == 8.4  # 区间合计 13.62/2、243.6/29
    assert t["lines"][0]["unit_price"] == 38.99  # T1 有申报单价列（盘点清单 §3 第 5 点写错了，已更正）
    assert sum(l["qty"] for l in t["lines"]) == 190


def test_T2_send():
    t = _one(_parse("T2"))
    assert t["shipment_id"] == "FBA19P4N6MM2" and t["box_count"] == 37
    assert t["boxes"][:23] == [7.5] * 23 and t["boxes"][23:] == [9.5] * 14
    assert [l["qty"] for l in t["lines"]] == [92, 56]


def test_T3_desu_batch9_weight_is_per_unit_fixed_by_csv():
    r = _parse("T3")
    t = _one(r)
    assert (t["shipment_id"], t["warehouse"], t["box_count"]) == ("FBA19GQXZW0N", "RFD2", 26)
    assert sum(l["qty"] for l in t["lines"]) == 104  # 每箱数量 4 × 26 箱
    assert t["boxes"][0] == 1.7025  # 按模板表头“单箱重量”读：1.7025 → 明显是单件重
    r2 = it.reconcile_with_csv(r, [_csv("第9批-FBA19GQXZW0N.csv")])
    t2 = _one(r2)
    # S4-fix1：只提建议，不自己改；确认后才生效
    assert t2["weight_meaning"] == "per_box" and t2["boxes"][0] == 1.7025 and t2["verify_status"] == "待确认"
    prop = [p for p in r2["proposals"] if p["field"] == "weight_meaning"]
    assert [p["proposed"] for p in prop] == ["per_unit"]
    t3 = _one(it.apply_corrections(r2, [prop[0]["id"]]))
    assert t3["weight_meaning"] == "per_unit" and t3["boxes"][0] == 6.81


def test_T3_desu_batch2_multi_sku_row_qty_is_row_total():
    t = _one(_parse("T3b"))
    assert (t["shipment_id"], t["warehouse"], t["box_count"], t["order_no"]) == ("FBA19CG4R0LP", "MCC1", 10, "JUS2MX33")
    assert sum(l["qty"] for l in t["lines"]) == 55  # 运费表数量 55；一行写多个 SKU 时不可能是每箱数量
    assert "qty_meaning_row_total_multi_sku" in {i["code"] for i in t["issues"]}


def test_T4_jiufang_old():
    r = _parse("T4")
    t = _one(r)
    assert (t["shipment_id"], t["warehouse"], t["box_count"]) == ("FBA19F49MKQW", "FWA4", 27)
    assert sum(l["qty"] for l in t["lines"]) == 99 and t["boxes"][0] == 16.5
    t2 = _one(it.reconcile_with_csv(r, [_csv("第4批-FBA19F49MKQW.csv")]))
    assert not [i for i in t2["issues"] if i["code"] in ("box_count_mismatch", "qty_mismatch", "warehouse_conflict")]


def test_T5_qiluo_single_row_summary():
    t = _one(_parse("T5", template_id="T5"))  # T5/T7 同分，必须手选
    assert (t["shipment_id"], t["warehouse"], t["box_count"]) == ("FBA19FS81Y33", "ORF2", 35)
    assert t["boxes"] is None and t["gross_kg"] == 294.0
    assert t["lines"][0]["qty"] == 210 and t["lines"][0]["unit_price"] == 39.99


def test_T6_qiluo_batch7_single_piece_weight_is_per_box():
    r = _parse("T6")
    t = _one(r)
    assert (t["shipment_id"], t["warehouse"], t["box_count"]) == ("FBA19GVFX5SC", "VGT2", 29)
    # D-09 第 2 点重写：不默认含义，没有 CSV 时不出单箱重
    assert sum(l["qty"] for l in t["lines"]) == 116 and t["boxes"] is None and t["weight_meaning"] is None
    assert "weight_meaning_undecided" in {i["code"] for i in t["issues"]} and t["verify_status"] == "未核对"
    t2 = _one(it.reconcile_with_csv(r, [_csv("第7批-FBA19GVFX5SC.csv")]))
    assert t2["weight_meaning"] == "per_box" and t2["boxes"][0] == 6.81
    assert [d["value"] for d in t2["decisions"] if d["field"] == "weight_meaning"] == ["per_box"]


def test_T6_batch6_ticket1_six_boxes_not_1_30_and_unit_weight_fixed_by_csv():
    r = _parse("T6b6t1")
    t = _one(r)
    assert t["box_count"] == 6 and "box_range_exceeds_forecast" in {i["code"] for i in t["issues"]}
    assert sum(l["qty"] for l in t["lines"]) == 30
    t2 = _one(it.reconcile_with_csv(r, [_csv("第6批-FBA19GDLZ88C.csv")]))
    assert t2["weight_meaning"] == "per_unit" and t2["boxes"] == [20.0] * 6


def test_T6_batch6_ticket5_warehouse_is_MGE3():
    r = _parse("T6b6t5")
    t = _one(r)
    assert t["warehouse"] == "MGE3"
    w = [i for i in t["issues"] if i["code"] == "warehouse_conflict"]
    assert w and "ACY2" in w[0]["message"] and "MGE3" in w[0]["message"]
    t2 = _one(it.reconcile_with_csv(r, [_csv("第6批-FBA19GDJR25Y.csv")]))
    assert t2["warehouse"] == "MGE3"
    # 配置成“以表内为准”时取 E3 的 ACY2（可配置，默认按证据多的一方）
    t3 = _one(_parse("T6b6t5", overrides={"warehouse_prefer": "sheet"}))
    assert t3["warehouse"] == "ACY2"


def test_T7_blank_variant():
    r = _parse("T7", template_id="T7")
    assert r["template_id"] == "T7" and r["tickets"] == []
    assert "blank_template" in {i["code"] for i in r["issues"]}


def test_T8_jiufang_export():
    t = _one(_parse("T8"))
    assert (t["shipment_id"], t["warehouse"], t["box_count"]) == ("FBA19JQTB2XL", "LAX9", 25)
    assert sum(l["qty"] for l in t["lines"]) == 100 and t["boxes"][0] == 4.4


def test_overrides_change_meanings():
    t = _one(_parse("T6", overrides={"weight_meaning": "per_unit"}))
    assert t["boxes"][0] == 27.24  # 6.81 × 4


def test_user_config_overrides_bundled(monkeypatch, tmp_path):
    p = tmp_path / "invoice_template_map.json"
    p.write_text('{"templates": {"T6": {"weight_meaning": "per_unit"}}}', encoding="utf-8")
    monkeypatch.setattr(it, "_user_config_path", lambda: p)
    assert {t["id"]: t for t in it.list_templates()}["T6"]["weight_meaning"] == "per_unit"
    assert _one(_parse("T6"))["boxes"][0] == 27.24


def test_to_customs_ticket_matches_customs_golden_input_JUS6HB30():
    r = it.reconcile_with_csv(_parse("T6b6t1"), [_csv("第6批-FBA19GDLZ88C.csv")])
    c = it.to_customs_ticket(_one(r))
    assert c["shipment_id"] == "FBA19GDLZ88C" and c["warehouse"] == "ILG1"
    assert c["boxes"] == [20.0] * 6
    assert [(l["chinese_name"], l["qty"], l["unit_price"]) for l in c["lines"]] == [("宠物围栏", 30.0, 69.99)]


def test_api_detect_and_parse():
    from fastapi.testclient import TestClient

    from main import app

    c = TestClient(app)
    p = SAMPLES["T6b6t5"]
    r = c.post("/api/invoice-templates/detect", files={"file": (p.name, p.read_bytes())})
    assert r.status_code == 200 and r.json()["template_id"] == "T6"
    r = c.post("/api/invoice-templates/parse", files={"file": (p.name, p.read_bytes())}, data={"template_id": "T6"})
    assert r.status_code == 200 and r.json()["tickets"][0]["warehouse"] == "MGE3"
    r = c.post("/api/invoice-templates/parse", files={"file": (p.name, p.read_bytes())}, data={"template_id": "T1"})
    assert r.status_code == 422
    assert len(c.get("/api/invoice-templates").json()["templates"]) == 8


@pytest.mark.parametrize("pattern,boxes,gross", [("*第五批*", 171, 1436.4), ("*第6批*", 30, 600.0)])
def test_batch_totals_match_customs_declaration(pattern, boxes, gross):
    """第5批（JUS5HB171）、第6批（JUS6HB30）：模板解析 + CSV 核对后的件数 / 毛重 = 历史报关单表头。"""
    from decimal import Decimal

    n, g = 0, Decimal("0")
    for p in sorted(LEG.glob(pattern)):
        r = it.parse_invoice_file(p.read_bytes(), p.name, template_id="T5" if "第五批" in p.name else None)
        csvs = [c.read_bytes() for c in INP.glob("*.csv") if any(c.stem.endswith(t["shipment_id"]) for t in r["tickets"])]
        if csvs:
            r = it.reconcile_with_csv(r, csvs)
        for t in r["tickets"]:
            n += t["box_count"]
            g += Decimal(str(t["gross_kg"]))
    assert (n, float(g)) == (boxes, gross)
