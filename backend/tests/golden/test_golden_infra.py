"""S1b golden 回归基建测试：manifest、快照、比对规则（方案 v7 §5.1）。"""
from decimal import Decimal
import json

import pytest

from tests._realdata import requires_realdata
from tests.golden import compare_golden as cg

G = cg.GOLDEN_DIR


@requires_realdata(G / "customs_manifest.csv", G / "invoice_manifest.csv")
def test_manifest_columns_and_counts():
    customs = cg.load_manifest(G / "customs_manifest.csv")
    invoice = cg.load_manifest(G / "invoice_manifest.csv")
    assert len(customs) == 38
    assert sum(r["level"] == "A" for r in customs) == 14
    assert sum(r["level"] == "B" for r in customs) == 24
    assert {r["kind"] for r in invoice} == {"invoice_send", "invoice_jiufang"}
    assert sum(r["kind"] == "invoice_send" for r in invoice) == 5
    assert sum(r["kind"] == "invoice_jiufang" for r in invoice) == 8
    for r in customs + invoice:
        assert (G / r["expected_path"]).exists(), r["expected_path"]


@requires_realdata(G / "invoice_manifest.csv")
def test_no_qiluo_or_legacy_in_golden():
    invoice = cg.load_manifest(G / "invoice_manifest.csv")
    assert all("琪珞" not in r["expected_path"] for r in invoice)


@requires_realdata(G / "product_master_golden.json")
def test_product_snapshot_declared_value_empty():
    snap = json.loads((G / "product_master_golden.json").read_text(encoding="utf-8"))
    products = snap["products"]
    assert products
    for p in products:
        assert p["declared_value"] is None
        assert p["listing_price"] > 0
        assert p["currency"] == "USD"


@requires_realdata(G / "customs_manifest.csv")
def test_expected_diff_contains_b1_q7_and_not_box_text():
    customs = {r["case_id"]: r for r in cg.load_manifest(G / "customs_manifest.csv")}
    d = cg.parse_expected_diff(customs["JUS14DD12"]["expected_diff"])
    assert "报关单!G12" in d and "报关单!F12" in d
    assert "合同!A33" in d and "委托书!E12" in d
    # 第15批文本件数不进 expected_diff（v7）
    for cid in ("JUS15DD5", "JUS15DD5SBD", "JUS15DD6", "JUS15DD6TEB", "JUS15DD8"):
        assert "报关单!E12" not in cg.parse_expected_diff(customs[cid]["expected_diff"])
    # 第13批毛重口径一致，不列 F12
    assert "报关单!F12" not in cg.parse_expected_diff(customs["JUS13DD21"]["expected_diff"])


@requires_realdata(G / "customs_manifest.csv")
@pytest.mark.parametrize(
    "cid,expected",
    [("JUS15DD5", 5), ("JUS15DD5SBD", 5), ("JUS15DD6", 6), ("JUS15DD6TEB", 6), ("JUS15DD8", 8)],
)
def test_batch15_box_text_cleaned_and_passes(cid, expected):
    customs = {r["case_id"]: r for r in cg.load_manifest(G / "customs_manifest.csv")}
    path = G / customs[cid]["expected_path"]
    raw = cg.read_cells(path, ["报关单!E12"])["报关单!E12"]
    assert raw == f"{expected}箱"
    assert cg.compare_value(raw, expected, kind="count") == cg.VERDICT_PASS_CLEANED


@requires_realdata(G / "customs_manifest.csv")
def test_freight_cell_k12_blank_in_all_samples():
    customs = cg.load_manifest(G / "customs_manifest.csv")
    for r in customs:
        cells = cg.read_cells(G / r["expected_path"], ["报关单!K11", "报关单!K12"])
        assert cells["报关单!K11"] == "运费"
        assert str(cells["报关单!K12"] or "").strip() == ""


def test_compare_rules():
    assert cg.compare_value(3679.2, Decimal("3679.20"), kind="money") == cg.VERDICT_PASS
    assert cg.compare_value(3679.16, Decimal("3679.20"), kind="money") == cg.VERDICT_FAIL
    assert cg.compare_value(112.8, 112.81, kind="weight") == cg.VERDICT_PASS
    assert cg.compare_value(112.8, 112.82, kind="weight") == cg.VERDICT_FAIL
    assert cg.compare_value("39.99", 39.99, kind="money") == cg.VERDICT_PASS
    assert cg.compare_value("50.0", 50, kind="text") == cg.VERDICT_PASS
    assert cg.compare_value(" 宠物垫 ", "宠物垫") == cg.VERDICT_PASS
    assert cg.compare_value(46205, "2026-07-02", kind="date") == cg.VERDICT_PASS
    assert cg.compare_value(None, "", kind="money") == cg.VERDICT_PASS


@requires_realdata(G / "invoice_manifest.csv")
def test_sheet_name_normalized():
    assert cg.find_sheet_name(["Invoice\xa0Template"], "Invoice Template") == "Invoice\xa0Template"
    sends = [r for r in cg.load_manifest(G / "invoice_manifest.csv") if r["kind"] == "invoice_send"]
    cells = cg.read_cells(G / sends[0]["expected_path"], ["Invoice Template!A14"])
    assert cells["Invoice Template!A14"] is not None


@requires_realdata(G / "customs_manifest.csv")
def test_known_diff_and_report(tmp_path):
    customs = {r["case_id"]: r for r in cg.load_manifest(G / "customs_manifest.csv")}
    r = customs["JUS13DD21"]
    exp = G / r["expected_path"]
    # 用期望文件自身做“实际文件”：全部通过，管道可用
    rows = cg.compare_files("JUS13DD21", exp, exp, cg.CUSTOMS_FIELDS_A, cg.parse_expected_diff(r["expected_diff"]))
    assert not cg.failures(rows)
    # 构造一个净重不同的结果：G12 在 expected_diff 里 → 已知差异
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "报关单"
    ws["G12"] = 1.0
    act = tmp_path / "act.xlsx"
    wb.save(act)
    rows = cg.compare_files("JUS13DD21", exp, act, {"报关单!G12": "weight", "报关单!I20": "money"}, cg.parse_expected_diff(r["expected_diff"]))
    verdicts = {x.ref: x.verdict for x in rows}
    assert verdicts["报关单!G12"] == cg.VERDICT_KNOWN
    assert verdicts["报关单!I20"] == cg.VERDICT_FAIL
    cg.write_report(rows, tmp_path / "report.csv")
    assert (tmp_path / "report.csv").read_text(encoding="utf-8-sig").count("\n") == 3


def test_warnings_compare():
    assert cg.compare_warnings("x", ["A", "B"], ["B", "A"])[0].verdict == cg.VERDICT_PASS
    assert cg.compare_warnings("x", ["A"], [])[0].verdict == cg.VERDICT_FAIL


@requires_realdata(G / "customs_manifest.csv")
def test_q3_invoice_sum_vs_customs_total_known_diff():
    """发票合计 3679.16 与报关总价 3679.20 的差额识别为已知差异（方案 v7 §5-7）。"""
    customs = {r["case_id"]: r for r in cg.load_manifest(G / "customs_manifest.csv")}
    d = cg.parse_expected_diff(customs["JUS13DD21"]["expected_diff"])
    assert "XCHK:发票合计≠报关总价" in d
    total = cg.read_cells(G / customs["JUS13DD21"]["expected_path"], ["报关单!J20"])["报关单!J20"]
    assert cg.compare_value(3679.16, total, kind="money") == cg.VERDICT_FAIL  # 数值确实不同
    assert Decimal(str(total)) == Decimal("84") * Decimal("43.80")


@requires_realdata(G / "invoice_manifest.csv")
def test_invoice_manifest_warnings_follow_new_price_rule():
    """s2-fix2：快照有 listing_price、declared_value 为空 → 来源 lingxing，不再期望回落警告。"""
    import csv
    from pathlib import Path

    p = Path(__file__).resolve().parents[2] / "tests" / "golden" / "invoice_manifest.csv"
    rows = list(csv.DictReader(p.open(encoding="utf-8-sig")))
    assert len(rows) == 13
    assert all("DECLARED_VALUE_FALLBACK" not in r["expected_warnings"] for r in rows)
    assert all(r["expected_warnings"].startswith("无") for r in rows)
