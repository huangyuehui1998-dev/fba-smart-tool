"""S9-step2-fix A1–A3：预览“确认写入后申报将用”的价格 == 写库后报关包里的单价。
覆盖 D-12 全部场景 × 手动（预览→确认）和定时（自动写入）两条路径；只变常规价也要写入。
全部 mock 领星，不调真实接口。"""
from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from test_s5_lingxing_schedule import _factory, env  # noqa: F401  (env 是 fixture)
from test_s8fix1_dec12_e2e import _customs, _row, _sync
from fba_tool import lingxing_scheduler as sched
from fba_tool import lingxing_sync as ls
from fba_tool.lingxing_preview import (apply_lingxing_field_patch, build_listing_preview, confirm_lingxing_preview,
                                       preview_price_info, serialize_preview, _num_or_none)
from fba_tool.master_db import get_product_by_sku
from fba_tool.product_fields import resolve_declared_price


def _expire(env, sku):
    old = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
    con = sqlite3.connect(env / "fba_master.db")
    con.execute("UPDATE product_master SET last_nonpromo_at=? WHERE sku=?", (old, sku))
    con.commit()
    con.close()


# (名称, 首次同步行 or None, 是否让历史过期, 第二次领星行参数, 期望申报价, 期望来源)
SCENARIOS = [
    ("regular_first_new", None, False, (15.99, 19.99), 19.99, "lingxing_regular"),
    ("fallback_nonpromo", (16.0, None), False, (12.0, None), 16.0, "lingxing_recent_nonpromo"),
    ("nonpromo_expired", (16.0, None), True, (12.0, None), 12.0, "lingxing"),
    ("unchanged", (15.99, 19.99), False, (15.99, 19.99), 19.99, "lingxing_regular"),
    ("only_regular_changes", (15.99, 15.99), False, (15.99, 19.99), 19.99, "lingxing_regular"),
    ("both_change", (15.99, 15.99), False, (14.0, 20.0), 20.0, "lingxing_regular"),
    ("regular_drops_to_price", (15.99, 19.99), False, (15.99, 15.99), 15.99, "lingxing"),
]


def _manual_preview(env, rows):
    list(ls.iter_full_sync_events(client=_factory(rows)()))
    con = sqlite3.connect(env / "fba_master.db")
    run_id = con.execute("SELECT MAX(id) FROM lingxing_sync_run").fetchone()[0]
    con.close()
    return run_id, serialize_preview(run_id)


def _item(pv, sku):
    for items in pv["groups"].values():
        for it in items:
            if it["sku"] == sku:
                return it
    raise AssertionError(f"{sku} 不在预览里")


@pytest.mark.parametrize("path", ["manual", "scheduled"])
@pytest.mark.parametrize("name,first,expire,second,expect,src", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_preview_price_equals_customs_unit_price(env, path, name, first, expire, second, expect, src):
    sku = "P-" + name.upper().replace("_", "-")[:20]
    ls.save_lingxing_settings(mcp_key="lxFAKE-TESTONLY-000")
    if first is not None:
        _sync([_row(sku, first[0], first[1])])
        if expire:
            _expire(env, sku)
    run_id, pv = _manual_preview(env, [_row(sku, second[0], second[1])])
    it = _item(pv, sku)
    shown = it["price_info"]
    assert shown["declared_price"] == pytest.approx(expect), shown
    assert shown["declared_source"] == src
    if path == "manual":
        fields = [f["field"] for f in it["fields"] if f["default_checked"]]
        confirm_lingxing_preview(run_id, [{"sku": sku, "fields": fields}] if fields else [])
    else:
        sched.auto_apply_preview(run_id)  # 定时同步写库用的同一个函数（按默认勾选）
    p = get_product_by_sku(sku)
    assert resolve_declared_price(p) == (pytest.approx(expect), src)
    assert _customs(sku).lines[0].unit_price == pytest.approx(shown["declared_price"])


def test_only_regular_change_is_offered_and_checked(env):
    _sync([_row("P-RO", 15.99, 15.99)])
    _run, pv = _manual_preview(env, [_row("P-RO", 15.99, 19.99)])
    it = _item(pv, "P-RO")
    assert it["group_kind"] == "changed"
    f = {x["field"]: x for x in it["fields"]}
    assert "regular_price" in f and f["regular_price"]["default_checked"] is True
    assert f["regular_price"]["label"] == "领星常规价（判断促销）"
    assert it["price_info"]["promo"] is True and it["price_info"]["promo_drop_pct"] == 20.0


def test_full_scheduled_run_once_writes_regular_only_change(env):
    _sync([_row("P-RS", 15.99, 15.99)])
    _sync([_row("P-RS", 15.99, 19.99)])  # 真正的定时任务 run_once（自动写入）
    p = get_product_by_sku("P-RS")
    assert p["regular_price"] == pytest.approx(19.99)
    assert _customs("P-RS").lines[0].unit_price == pytest.approx(19.99)


def test_unchecking_regular_updates_shown_price_and_matches_customs(env):
    _sync([_row("P-UN", 15.99, 15.99)])
    run_id, pv = _manual_preview(env, [_row("P-UN", 15.99, 19.99)])
    info = _item(pv, "P-UN")["price_info"]
    assert info["default_key"] == "regular_price"
    assert info["variants"][""]["declared_price"] == pytest.approx(15.99)
    confirm_lingxing_preview(run_id, [])  # 用户取消勾选常规价，什么都不写
    assert _customs("P-UN").lines[0].unit_price == pytest.approx(info["variants"][""]["declared_price"])


def test_unchecking_listing_price_variant(env):
    _sync([_row("P-UL", 16.0, None)])
    run_id, pv = _manual_preview(env, [_row("P-UL", 12.0, 12.0)])
    info = _item(pv, "P-UL")["price_info"]
    assert set(info["price_fields"]) == {"listing_price", "regular_price"}
    both = info["variants"]["listing_price+regular_price"]
    assert both["declared_price"] == pytest.approx(16.0) and both["declared_source"] == "lingxing_recent_nonpromo"
    only_rp = info["variants"]["regular_price"]  # 不写售价：仍是本地 16，常规价 12 不高于售价
    assert only_rp["declared_price"] == pytest.approx(16.0) and only_rp["declared_source"] == "lingxing"
    confirm_lingxing_preview(run_id, [{"sku": "P-UL", "fields": ["regular_price"]}])
    p = get_product_by_sku("P-UL")
    assert p["listing_price"] == pytest.approx(16.0) and p["regular_price"] == pytest.approx(12.0)
    assert _customs("P-UL").lines[0].unit_price == pytest.approx(only_rp["declared_price"])


def test_listing_only_does_not_write_regular(env):
    _sync([_row("P-LO", 15.99, 15.99)])
    run_id, pv = _manual_preview(env, [_row("P-LO", 14.0, 20.0)])
    info = _item(pv, "P-LO")["price_info"]
    lp_only = info["variants"]["listing_price"]
    confirm_lingxing_preview(run_id, [{"sku": "P-LO", "fields": ["listing_price"]}])
    p = get_product_by_sku("P-LO")
    assert p["regular_price"] == pytest.approx(15.99)
    assert _customs("P-LO").lines[0].unit_price == pytest.approx(lp_only["declared_price"])


# ---------------- A2：常规价来源如实显示 ----------------
def test_regular_origin_local_when_lingxing_omits_it():
    existing = {"sku": "S", "listing_price": 15.99, "regular_price": 19.99, "listing_price_basis": "listing_price"}
    info = preview_price_info({"listing_price": 15.99}, existing)
    assert info["regular_price"] == pytest.approx(19.99)
    assert info["regular_price_origin"] == "local"
    assert info["declared_source_label"] == "正常价 · 领星常规价" and info["promo"] is True


def test_regular_origin_remote_when_written():
    info = preview_price_info({"listing_price": 15.99, "regular_price": 19.99}, {"sku": "S", "regular_price": 18.0})
    assert info["regular_price_origin"] == "remote" and info["regular_price"] == pytest.approx(19.99)


def test_currency_carried():
    info = preview_price_info({"listing_price": 12.0, "listing_price_currency": "usd"}, None)
    assert info["currency"] == "USD"


# ---------------- A3：价格解析健壮 ----------------
@pytest.mark.parametrize("raw,expect", [
    ("1,299.00", 1299.0), ("$12.50", 12.5), (15.99, 15.99),
    ("abc", None), ("nan", None), ("NaN", None), (float("nan"), None), ("inf", None), (float("inf"), None),
    ("-3", None), (-3, None), (0, None), ("0", None), ("", None), (None, None), (True, None),
])
def test_num_or_none(raw, expect):
    assert _num_or_none(raw) == expect


def test_parse_price_and_price_or_none_nan_inf():
    from fba_tool.lingxing_adapter import parse_price

    for raw in ("nan", "NaN", "inf", "-inf", "Infinity", float("nan")):
        assert parse_price(raw) is None
        assert ls._price_or_none(raw) is None
    assert ls._price_or_none("1,299.00") == 1299.0


@pytest.mark.parametrize("bad", ["abc", "nan", float("nan"), "inf", -5, 0, "", "1,2,3x"])
def test_invalid_remote_price_keeps_local_and_warns(bad):
    existing = {"sku": "S", "listing_price": 10.0, "listing_price_basis": "listing_price"}
    info = preview_price_info({"listing_price": bad, "regular_price": bad}, existing)
    assert info["declared_price"] == pytest.approx(10.0)
    assert info["listing_price_origin"] == "local"
    for v in info["variants"].values():
        assert v["declared_price"] is None or math.isfinite(v["declared_price"])
    if bad not in ("", None):
        assert any("无效" in w for w in info["warnings"])


def test_no_valid_price_declares_none_not_zero():
    info = preview_price_info({"listing_price": 0}, {"sku": "S", "listing_price": 0})
    assert info["declared_price"] is None
    assert any("没有有效的申报价" in w for w in info["warnings"])
    assert resolve_declared_price({"listing_price": 0}) == (None, "")
    assert resolve_declared_price({"listing_price": float("nan")}) == (None, "")


def test_preview_and_apply_with_invalid_prices_no_500(env):
    from fastapi.testclient import TestClient
    from main import app

    _sync([_row("P-BAD", 10.0, None)])
    con = sqlite3.connect(env / "fba_master.db")
    run_id = con.execute("SELECT MAX(id) FROM lingxing_sync_run").fetchone()[0]  # 真实存在的拉取记录，接口才不 404
    con.close()
    build_listing_preview(run_id, [{"sku": "P-BAD", "asin": "B0DEMOBAD1", "fnsku": "X0DEMOBAD1",
                                    "listing_price": "abc", "regular_price": "nan"}])
    pv = serialize_preview(run_id)
    it = _item(pv, "P-BAD")
    assert "listing_price" not in {f["field"] for f in it["fields"]}
    assert it["price_info"]["declared_price"] == pytest.approx(10.0)
    res = apply_lingxing_field_patch("P-BAD", ["listing_price", "regular_price"], {"listing_price": "abc", "regular_price": "inf"})
    assert set(res["skipped_invalid"]) == {"listing_price", "regular_price"}
    assert get_product_by_sku("P-BAD")["listing_price"] == pytest.approx(10.0)
    r = TestClient(app).get("/api/lingxing/sync/preview", params={"run_id": run_id})
    assert r.status_code == 200, r.text
