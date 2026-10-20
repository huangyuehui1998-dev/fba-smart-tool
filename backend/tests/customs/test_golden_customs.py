"""S3-5 报关 golden 回归（方案 v8 §5.1、3.6 验收 1/2）：38 份样例按 manifest 逐字段比对，.xlsx 和 .xls 各跑一遍，“失败”必须为 0。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fba_tool import customs_package as cp
from fba_tool.customs_export import export_customs_package
from fba_tool.customs_package import build_customs_from_tickets
from tests._realdata import skip_module_if_missing
from tests.golden import compare_golden as cg

G = cg.GOLDEN_DIR
skip_module_if_missing(G / "customs_inputs.json", G / "customs_manifest.csv")
TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "customs" / "报关资料模板.xlsx"
INPUTS = json.loads((G / "customs_inputs.json").read_text(encoding="utf-8"))
MANIFEST = {r["case_id"]: r for r in cg.load_manifest(G / "customs_manifest.csv")}
B_WEIGHT_EXEMPT = {"gross_not_positive", "net_not_positive"}
PROFILE = {"id": "golden", "name": "武汉花屿森电子商务有限公司", "credit_code": "91420113MACWNNKU99", "signed_at": "武汉", "domestic_source": "武汉"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    ad = tmp_path / "ad"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    from fba_tool.master_db import init_master_db

    init_master_db()
    monkeypatch.setattr(cp, "_catalog_hints", lambda sku: {})


def _expected_warnings(text: str):
    t = (text or "").strip()
    return [] if not t or t.startswith("无") else [w.strip() for w in t.split(";") if w.strip()]


def run_case(cid: str, fmt: str, tmp: Path):
    case = INPUTS[cid]
    m = MANIFEST[cid]
    data = build_customs_from_tickets(case["tickets"], PROFILE, order_no=case["order_no"])
    out = tmp / f"{cid}.{fmt}"
    # 测试专用豁免：B 级样例没有重量（F12 空），只比结构字段，豁免“毛重/净重 > 0”；A 级不豁免
    exempt = B_WEIGHT_EXEMPT if m["level"] == "B" else None
    out.write_bytes(export_customs_package(data, TEMPLATE.read_bytes(), fmt=fmt, _test_exempt_codes=exempt))
    fields = cg.CUSTOMS_FIELDS_A if m["level"] == "A" else cg.CUSTOMS_FIELDS_B
    rows = cg.compare_files(cid, G / m["expected_path"], out, fields, cg.parse_expected_diff(m["expected_diff"]))
    rows += cg.compare_warnings(cid, _expected_warnings(m["expected_warnings"]), [w["code"] for w in data.warnings])
    return rows


def test_inputs_cover_manifest():
    assert set(INPUTS) == set(MANIFEST)
    assert sum(v["level"] == "A" for v in INPUTS.values()) == 14
    for cid, v in INPUTS.items():
        for p in v["inputs"]:
            assert (G / p).is_file(), (cid, p)


@pytest.mark.parametrize("fmt", ["xlsx", "xls"])
def test_customs_golden_zero_failures(fmt, tmp_path):
    rows = []
    for cid in sorted(MANIFEST):
        rows += run_case(cid, fmt, tmp_path)
    cg.write_report(rows, tmp_path / f"customs_golden_{fmt}.csv")
    fails = cg.failures(rows)
    assert not fails, "\n".join(f"{r.case_id} {r.ref} 期望={r.expected!r} 实际={r.actual!r}" for r in fails)
    known = [r for r in rows if r.verdict == cg.VERDICT_KNOWN]
    assert known, "应有已知差异（净重口径、口岸、委托书有效期）"
    assert any(r.verdict == cg.VERDICT_PASS_CLEANED for r in rows)  # 第 15 批“N箱”清洗后通过


@pytest.mark.parametrize("cid,gross,net", [("JUS13DD21", 173.5, 169.3), ("JUS14DD12", 112.8, 110.4)])
def test_known_weight_values(cid, gross, net, tmp_path):
    d = build_customs_from_tickets(INPUTS[cid]["tickets"], PROFILE, order_no=cid)
    assert (d.total_gross_kg, d.total_net_kg) == (gross, net)


def test_q3_total_vs_invoice_sum():
    d = build_customs_from_tickets(INPUTS["JUS13DD21"]["tickets"], PROFILE, order_no="JUS13DD21")
    assert d.lines[0].unit_price == 43.80 and d.total_amount == 3679.20


def test_b_level_without_exemption_is_blocked():
    """B 级不给豁免就会被“毛重 > 0”拦下，说明拦截在正式导出里生效。"""
    from fba_tool.customs_export import CustomsExportBlocked

    cid = next(c for c, v in INPUTS.items() if v["level"] == "B")
    data = build_customs_from_tickets(INPUTS[cid]["tickets"], PROFILE, order_no=cid)
    with pytest.raises(CustomsExportBlocked):
        export_customs_package(data, TEMPLATE.read_bytes())


@pytest.mark.parametrize("cid,needle", [("JUS14DD28", "差 4 kg"), ("JUS11DD25W", "约 10 kg")])
def test_jiufang_sample_inconsistency_documented(cid, needle):
    d = cg.parse_expected_diff(MANIFEST[cid]["expected_diff"])
    assert needle in d["报关单!G12"] and "九方样例自己对不上" in d["报关单!G12"]
