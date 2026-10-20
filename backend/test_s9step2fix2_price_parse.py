"""S9-step2-fix2 N1–N3：统一价格解析（预览、定时同步、Excel 导入三条路径共用 parse_price）。
欧式 / 不规范逗号写法、科学计数法、超大数、四舍五入后为 0 的值一律无效：不写入、给提示（显示原始值），
单行出问题只跳过这一行，整批继续；导入非法价格返回 422（带行号和原始值，不露内部类名）。全部 mock 领星。"""
from __future__ import annotations

import csv
import io
import sqlite3

import pytest

from test_s5_lingxing_schedule import _factory, env  # noqa: F401  (env 是 fixture)
from test_s8fix1_dec12_e2e import _row, _sync
from fba_tool import lingxing_sync as ls
from fba_tool.lingxing_adapter import PRICE_MAX, map_listing_row, parse_price, parse_price_reason
from fba_tool.lingxing_preview import preview_price_info, promo_drop_text, serialize_preview
from fba_tool.master_db import get_product_by_sku
from fba_tool.product_fields import _valid_price, resolve_declared_price

BIG_NINES = "9" * 40
BAD = ["12,5", "1.299,00", "$1,2", "1,2,3", "1,2345.00", "12,50", "1e30", BIG_NINES, "1e20", "1e3", "1e-3", "0.004",
       "1E+2", "abc", "nan", "inf", "-5", "0", "100000.01"]


@pytest.mark.parametrize("raw,expect", [
    ("1,299.00", 1299.0), ("$1,299.00", 1299.0), ("USD 1,299", 1299.0), ("US$12", 12.0), ("USD$12.5", 12.5),
    ("12", 12.0), ("12.50", 12.5), (" 12 ", 12.0), ("１２", 12.0), ("0.01", 0.01), (15.99, 15.99), (12, 12.0),
    ("100000", 100000.0), ("12,345,678.9", None),
])
def test_valid_prices(raw, expect):
    assert parse_price(raw) == expect


@pytest.mark.parametrize("raw", BAD + [1e30, 1e20, float("nan"), float("inf"), True, 100000.5])
def test_invalid_prices_return_none_with_reason(raw):
    price, reason = parse_price_reason(raw)
    assert price is None and reason


def test_reasons_are_specific():
    assert "欧式" in parse_price_reason("12,5")[1]
    assert "欧式" in parse_price_reason("1.299,00")[1]
    assert "科学计数法" in parse_price_reason("1e30")[1]
    assert "上限" in parse_price_reason(BIG_NINES)[1]
    assert "为 0" in parse_price_reason("0.004")[1]
    assert PRICE_MAX == 100000.0


def test_map_listing_row_records_issue_and_never_raises():
    for raw in BAD:
        out = map_listing_row({"msku": "A", "listing_price": raw})
        assert out["listing_price"] is None, raw
    out = map_listing_row({"msku": "A", "listing_price": "12,5"})
    assert out["price_issues"][0]["raw"] == "12,5"
    ok = map_listing_row({"msku": "A", "listing_price": "1,299.00"})
    assert ok["listing_price"] == 1299.0 and "price_issues" not in ok


def test_valid_price_used_for_declaration():
    assert _valid_price("12,5") is None and _valid_price("1.299,00") is None
    assert _valid_price(1e20) is None and _valid_price(float("nan")) is None
    assert _valid_price(15.999) == 15.999  # 库里的数不四舍五入
    assert resolve_declared_price({"listing_price": 1e20}) == (None, "")
    assert resolve_declared_price({"listing_price": "1,299.00"}) == (pytest.approx(1299.0), "lingxing")


# ---------------- 定时同步 / 手动同步：单行问题不拖垮整批 ----------------
@pytest.mark.parametrize("raw", ["12,5", "1.299,00", "1e30", BIG_NINES, "1e20", "1e-3", "0.004"])
def test_scheduled_sync_skips_bad_price_row_and_continues(env, raw):
    _sync([_row("P-OK", 15.0, None), _row("P-BAD", 15.0, None)])
    res = _sync([_row("P-OK", 16.0, None), _row("P-BAD", raw, None)])
    assert res["ok"] and res["attempts"] == 1
    assert get_product_by_sku("P-OK")["listing_price"] == pytest.approx(16.0)
    assert get_product_by_sku("P-BAD")["listing_price"] == pytest.approx(15.0)  # 保留原值
    con = sqlite3.connect(env / "fba_master.db")
    diffs = con.execute("SELECT kind, sku, message FROM lingxing_sync_diff WHERE run_id=?", (res["run_id"],)).fetchall()
    con.close()
    bad = [d for d in diffs if d[0] == "price_invalid" and d[1] == "P-BAD"]
    assert bad and raw[:40] in bad[0][2], diffs
    assert all("InvalidOperation" not in d[2] and "class" not in d[2] for d in diffs)


def test_row_exception_skips_only_that_row(env, monkeypatch):
    real = ls.listing_to_product

    def boom(row, synced_at):
        if row.get("msku") == "P-BOOM":
            raise ArithmeticError("boom")
        return real(row, synced_at)

    monkeypatch.setattr(ls, "listing_to_product", boom)
    res = _sync([_row("P-FINE", 11.0, None), _row("P-BOOM", 12.0, None)])
    assert res["ok"] and res["attempts"] == 1
    assert get_product_by_sku("P-FINE")["listing_price"] == pytest.approx(11.0)
    assert get_product_by_sku("P-BOOM") is None
    con = sqlite3.connect(env / "fba_master.db")
    kinds = [r[0] for r in con.execute("SELECT kind FROM lingxing_sync_diff WHERE run_id=?", (res["run_id"],))]
    con.close()
    assert "row_skipped" in kinds


def test_manual_preview_shows_raw_value_and_does_not_offer_field(env):
    _sync([_row("P-EU", 15.0, 18.0)])
    list(ls.iter_full_sync_events(client=_factory([_row("P-EU", "12,5", "1e-3")])()))
    con = sqlite3.connect(env / "fba_master.db")
    run_id = con.execute("SELECT MAX(id) FROM lingxing_sync_run").fetchone()[0]
    con.close()
    pv = serialize_preview(run_id)
    it = [r for g in pv["groups"].values() for r in g if r["sku"] == "P-EU"][0]
    fields = {f["field"] for f in it["fields"]}
    assert "listing_price" not in fields and "regular_price" not in fields
    info = it["price_info"]
    assert info["declared_price"] == pytest.approx(18.0)  # 本地 15/18 → 促销，按正常价 18；领星的坏值不参与
    joined = " ".join(info["warnings"])
    assert "12,5" in joined and "1e-3" in joined and "保留原值" in joined


# ---------------- Excel / CSV 导入 ----------------
def _csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["MSKU", "FNSKU", "ASIN", "价格"])
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8-sig")


@pytest.mark.parametrize("raw", ["12,5", "1.299,00", "$1,2", "1e30", BIG_NINES, "1e20", "1e-3", "0.004"])
def test_import_bad_price_row_skipped_with_row_and_raw(env, raw):
    from fastapi.testclient import TestClient
    from main import app

    c = TestClient(app)
    data = _csv([["IMP-OK", "X0DEMOIMP1", "B0DEMOIMP1", "1,299.00"], ["IMP-BAD", "X0DEMOIMP2", "B0DEMOIMP2", raw]])
    r = c.post("/api/master-data/import/listing/preview", files={"file": ("l.csv", data, "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["new"] == 1  # 好的一行照常
    err = [e for e in body["errors"] if e["field"] == "listing_price"]
    assert err and err[0]["row"] == 3 and err[0]["value"] == raw
    # S9-step3 #1：确认写入只跳过坏行，合法行照常写入；响应列出跳过的行和原始值
    r = c.post("/api/master-data/import/listing/apply", files={"file": ("l.csv", data, "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["written"] == 1 and body["skipped_rows"] == [3]
    assert body["skipped"][0]["row"] == 3 and body["skipped"][0]["value"] == raw and "已跳过" in body["skipped"][0]["message"]
    assert "InvalidOperation" not in r.text and "Error" not in r.text
    assert get_product_by_sku("IMP-BAD") is None
    assert get_product_by_sku("IMP-OK")["listing_price"] == pytest.approx(1299.0)


def test_import_unexpected_error_is_422_without_class_name(env, monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    import fba_tool.product_import as pi

    def boom(data, name):
        raise ArithmeticError("decimal.InvalidOperation [<class 'decimal.InvalidOperation'>]")

    monkeypatch.setattr(pi, "preview_listing_import", boom)
    r = TestClient(app).post("/api/master-data/import/listing/preview",
                             files={"file": ("l.csv", _csv([["A", "X", "B", "1"]]), "text/csv")})
    assert r.status_code == 422
    assert "InvalidOperation" not in r.text and "class" not in r.text


def test_import_thousands_ok(env):
    from fba_tool.product_import import apply_listing_import

    apply_listing_import(_csv([["IMP-K", "X0DEMOIMPK", "B0DEMOIMPK", "1,299.00"]]), "l.csv")
    assert get_product_by_sku("IMP-K")["listing_price"] == pytest.approx(1299.0)


# ---------------- UI(g)、UI(e)、UI(a) 后端字段 ----------------
@pytest.mark.parametrize("lp,normal,text", [
    # S9-step3 UI(j)：统一 1 位小数（向下取）、“低”后加空格；实际 >5% 但取整为 5.0 时注明已超过阈值
    (18.99, 19.99, "低约 5.0%（已超过 5% 阈值）"),  # 实际 5.0025%
    (18.98, 20.0, "低 5.1%"),
    (18.9, 20.0, "低 5.5%"),
    (15.99, 19.99, "低 20.0%"),     # 20.01% 向下取
    (12.0, 16.0, "低 25.0%"),
    (14.0, 20.0, "低 30.0%"),
])
def test_promo_drop_text(lp, normal, text):
    assert promo_drop_text(lp, normal) == text


def test_price_info_flags_and_terms():
    info = preview_price_info({"listing_price": 15.99, "regular_price": 19.99}, None)
    assert info["promo"] and info["declared_above_listing"] is True
    assert info["promo_drop_text"] == "低 20.0%"
    assert info["declared_source_label"] == "正常价 · 领星常规价"
    assert info["normal_basis_label"] == "领星常规价"
    plain = preview_price_info({"listing_price": 15.99, "regular_price": 15.99}, None)
    assert plain["declared_above_listing"] is False and plain["declared_source_label"] == "售价"
