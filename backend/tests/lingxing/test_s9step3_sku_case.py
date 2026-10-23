"""S9-step3：SKU / MSKU 大小写统一。存储保留原始写法；匹配一律 sku_key（NFKC + 去首尾空白 + casefold）；
只差大小写的多个候选又没有原样相同的 → 报冲突，不静默任选；旧库里的重复不自动合并，只提示。示例数据，临时库。"""
from __future__ import annotations

import sqlite3

import pytest

from test_s5_lingxing_schedule import _factory, env  # noqa: F401  (env 是 fixture)
from test_s8fix1_dec12_e2e import _row, _sync
from fba_tool import lingxing_sync as ls
from fba_tool.fnsku_resolve import build_fnsku_map, resolve_fnsku
from fba_tool.master_db import (
    delete_product_by_sku,
    get_product_by_sku,
    get_products_by_skus,
    list_sku_case_conflicts,
    resolve_stored_sku,
    sku_conflicts_for,
    upsert_product,
)
from fba_tool.product_fields import SOURCE_LINGXING, set_product_fields
from fba_tool.sku_keys import SkuCaseConflict, case_conflicts, lookup_sku, lookup_sku_detail, sku_key


def _count(env, key):
    con = sqlite3.connect(env / "fba_master.db")
    rows = [r[0] for r in con.execute("SELECT sku FROM product_master")]
    con.close()
    return [s for s in rows if sku_key(s) == sku_key(key)]


def _raw_insert(env, *skus):
    con = sqlite3.connect(env / "fba_master.db")
    for s in skus:
        con.execute("INSERT INTO product_master (sku, updated_at) VALUES (?, '2026-01-01T00:00:00+00:00')", (s,))
    con.commit()
    con.close()


# ---------------- 公共函数 ----------------
@pytest.mark.parametrize("raw,key", [
    ("DEMO-Case-01", "demo-case-01"), ("  demo-case-01\t", "demo-case-01"), ("ＤＥＭＯ－ＣＡＳＥ－０１", "demo-case-01"),
    ("\u3000Demo-Case-01\u00a0", "demo-case-01"), ("DEMO-STRASSE", "demo-strasse"), ("DEMO-STRAßE", "demo-strasse"),
])
def test_sku_key(raw, key):
    assert sku_key(raw) == key


def test_lookup_rules():
    m = {"DEMO-A": 1, "demo-b": 2, "DEMO-B": 3}
    assert lookup_sku(m, "demo-a") == 1 and lookup_sku_detail(m, "demo-a")[1] == "normalized"
    assert lookup_sku(m, "DEMO-A") == 1 and lookup_sku_detail(m, "DEMO-A")[1] == "exact"
    assert lookup_sku(m, "demo-b") == 2  # 原样相同优先
    val, how, cands = lookup_sku_detail(m, "Demo-B")
    assert val is None and how == "ambiguous" and cands == ["DEMO-B", "demo-b"]
    assert lookup_sku(m, "Demo-B", "none") == "none"
    assert case_conflicts(["A1", "a1", " A1 ", "b"]) == {"a1": ["A1", "a1"]}


# ---------------- 数据库匹配 ----------------
def test_mixed_case_fullwidth_spaces_match_stored(env):
    upsert_product({"sku": "DEMO-CASE-01", "asin": "B0DEMOCASE"})
    for q in ("demo-case-01", "Demo-Case-01", "  DEMO-CASE-01 ", "ＤＥＭＯ－ＣＡＳＥ－０１", "demo-case-01\u3000"):
        rec = get_product_by_sku(q)
        assert rec and rec["sku"] == "DEMO-CASE-01", q  # 原始写法保留（显示、导出用）
    got = get_products_by_skus(["demo-case-01"])
    assert got["demo-case-01"]["sku"] == "DEMO-CASE-01"  # 以输入的 SKU 为键


def test_writes_go_to_stored_row_no_duplicate(env):
    upsert_product({"sku": "DEMO-CASE-02"})
    set_product_fields("demo-case-02", {"listing_price": 12.5}, SOURCE_LINGXING)  # 以前 UPDATE 按原样比对，静默不写
    upsert_product({"sku": "Demo-Case-02", "chinese_name": "示例品名"})  # 以前会新建一行
    assert _count(env, "DEMO-CASE-02") == ["DEMO-CASE-02"]
    rec = get_product_by_sku("DEMO-CASE-02")
    assert rec["listing_price"] == pytest.approx(12.5) and rec["chinese_name"] == "示例品名"
    assert rec["field_sources"].get("listing_price") == "lingxing"


def test_legacy_duplicates_conflict_not_merged(env):
    _raw_insert(env, "DEMO-DUP", "demo-dup")
    assert list_sku_case_conflicts() == [["DEMO-DUP", "demo-dup"]]
    assert get_product_by_sku("demo-dup")["sku"] == "demo-dup"   # 原样相同优先
    assert get_product_by_sku("DEMO-DUP")["sku"] == "DEMO-DUP"
    assert get_product_by_sku("Demo-Dup") is None                 # 多个候选、没有原样相同的 → 不任选
    with pytest.raises(SkuCaseConflict) as ei:
        resolve_stored_sku("Demo-Dup")
    assert ei.value.candidates == ["DEMO-DUP", "demo-dup"] and "没有自动选择" in str(ei.value)
    with pytest.raises(SkuCaseConflict):
        set_product_fields("Demo-Dup", {"listing_price": 9.9}, SOURCE_LINGXING)
    with pytest.raises(SkuCaseConflict):
        upsert_product({"sku": "Demo-Dup", "chinese_name": "x"})
    with pytest.raises(SkuCaseConflict):
        delete_product_by_sku("Demo-Dup")
    assert sku_conflicts_for(["Demo-Dup", "demo-dup", "DEMO-X"]) == {"Demo-Dup": ["DEMO-DUP", "demo-dup"]}
    assert sorted(_count(env, "demo-dup")) == ["DEMO-DUP", "demo-dup"]   # 不自动合并
    assert delete_product_by_sku("demo-dup") and _count(env, "demo-dup") == ["DEMO-DUP"]  # 只删匹配到的那一条


def test_list_api_reports_conflicts(env):
    from fastapi.testclient import TestClient
    from main import app

    _raw_insert(env, "DEMO-API", "demo-api")
    c = TestClient(app)
    body = c.get("/api/master-data/list").json()
    assert body["sku_case_conflicts"] == [["DEMO-API", "demo-api"]]
    r = c.delete("/api/master-data/sku/Demo-Api")
    assert r.status_code == 409 and "只差大小写" in r.json()["detail"]


def test_customs_price_checks_warn_conflict(env):
    from fba_tool.customs_package import price_checks

    _raw_insert(env, "DEMO-CUS", "demo-cus")
    _src, warnings, _blk = price_checks([{"sku": "Demo-Cus", "price_source": "none", "unit_price": 0.0}])
    w = [x for x in warnings if x["code"] == "sku_case_conflict"]
    assert w and "DEMO-CUS" in w[0]["message"] and "demo-cus" in w[0]["message"]


# ---------------- 领星同步 ----------------
def test_lingxing_mixed_case_updates_existing(env):
    _sync([_row("DEMO-LX-01", 15.0, None)])
    _sync([_row("demo-lx-01", 16.0, None)])
    assert _count(env, "DEMO-LX-01") == ["DEMO-LX-01"]
    assert get_product_by_sku("DEMO-LX-01")["listing_price"] == pytest.approx(16.0)


def test_lingxing_batch_case_conflict_needs_review(env):
    res = _sync([_row("DEMO-LX-CF", 15.0, None), _row("demo-lx-cf", 16.0, None)])
    run_id = res["run_ids"][-1]
    assert _count(env, "demo-lx-cf") == []  # 不自动写，也不自动合并
    con = sqlite3.connect(env / "fba_master.db")
    kinds = [r[0] for r in con.execute("SELECT kind FROM lingxing_sync_diff WHERE run_id=?", (run_id,))]
    con.close()
    assert "sku_case_conflict" in kinds
    from fba_tool.lingxing_preview import serialize_preview

    pv = serialize_preview(run_id)
    rows = pv["groups"]["needs_review"]
    assert {r["sku"] for r in rows} == {"DEMO-LX-CF", "demo-lx-cf"}
    assert all(any("只差大小写" in x for x in r["review_reasons"]) for r in rows)
    assert all(not f["default_checked"] for r in rows for f in r["fields"])


def test_lingxing_local_legacy_conflict_needs_review(env):
    from test_s5_lingxing_schedule import FAKE_KEY

    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    _raw_insert(env, "DEMO-LOC", "demo-loc")
    events = list(ls.iter_full_sync_events(client=_factory([_row("Demo-Loc", 15.0, None)])()))
    con = sqlite3.connect(env / "fba_master.db")
    run_id = con.execute("SELECT MAX(id) FROM lingxing_sync_run").fetchone()[0]
    msgs = [r[0] for r in con.execute("SELECT message FROM lingxing_sync_diff WHERE run_id=? AND kind='sku_case_conflict'", (run_id,))]
    con.close()
    assert any("产品库里有只差大小写" in m for m in msgs), (msgs, events[-3:])
    from fba_tool.lingxing_preview import confirm_lingxing_preview, serialize_preview

    pv = serialize_preview(run_id)
    row = [r for r in pv["groups"]["needs_review"] if r["sku"] == "Demo-Loc"][0]
    assert any("DEMO-LOC" in x and "demo-loc" in x for x in row["review_reasons"])
    out = confirm_lingxing_preview(run_id, [{"sku": "Demo-Loc", "fields": ["listing_price"]}])
    assert out["skipped"] == 1 and out["skus_patched"] == 0
    assert get_product_by_sku("DEMO-LOC")["listing_price"] is None and get_product_by_sku("demo-loc")["listing_price"] is None


# ---------------- 其他匹配点 ----------------
def test_fnsku_resolve_case_insensitive_and_conflict():
    assert resolve_fnsku("demo-fn", master_map={"DEMO-FN": "X00TEST001"}, json_map={}) == "X00TEST001"
    assert resolve_fnsku("Demo-Fn", master_map={"DEMO-FN": "X00TEST001", "demo-fn": "X00TEST002"}, json_map={}) == ""
    assert resolve_fnsku("demo-fn", master_map={"DEMO-FN": "X00TEST001", "demo-fn": "X00TEST002"}, json_map={}) == "X00TEST002"
    assert build_fnsku_map(["ＤＥＭＯ－ＦＮ"], step1_map={"DEMO-FN": "X00TEST003"}, master_map={}, json_map={}) == {
        "ＤＥＭＯ－ＦＮ": "X00TEST003"}


def test_shipment_cross_check_key_and_display():
    from fba_tool.shipment_cross_check import _norm_sku

    assert _norm_sku("ｄｅｍｏ - Ab 1") == _norm_sku("DEMO-AB1") == "demo-ab1"


def test_master_flags_use_input_key(env):
    from fba_tool.master_data_apply import resolve_sku_master_flags

    upsert_product({"sku": "DEMO-FLAG", "carton_length": 40, "carton_width": 30, "carton_height": 20})
    assert resolve_sku_master_flags(["demo-flag"]) == {"demo-flag": "official"}


def test_product_edit_duplicate_rows_case_insensitive(env):
    import io

    from openpyxl import Workbook

    from fba_tool.product_edit import preview_products_edit

    upsert_product({"sku": "DEMO-ED"})
    wb = Workbook()
    ws = wb.active
    ws.append(["sku", "chinese_name"])
    ws.append(["DEMO-ED", "甲"])
    ws.append(["demo-ed", "乙"])
    buf = io.BytesIO()
    wb.save(buf)
    pv = preview_products_edit(buf.getvalue(), "e.xlsx")
    assert len([e for e in pv["errors"] if "重复" in e["message"]]) == 2
