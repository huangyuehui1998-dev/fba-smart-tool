"""S8-fix1 N1：D-12 端到端——mock 领星同步 → 写库 → 从库读产品 → 申报价 / 价格来源 → 报关包提示。
不直接喂 dict：每条都经过 get_product_by_sku（_row_to_dict），这是上轮漏掉的环节。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from test_s5_lingxing_schedule import FAKE_KEY, _factory, env  # noqa: F401  (env 是 fixture)
from fba_tool import lingxing_scheduler as sched
from fba_tool import lingxing_sync as ls
from fba_tool.master_db import lookup_by_fnsku, get_product_by_sku
from fba_tool.product_fields import promo_info, resolve_declared_price

PROFILE = {"id": "t", "name": "测试公司", "credit_code": "X", "signed_at": "武汉", "domestic_source": "武汉"}


def _row(sku, price, regular=None, fnsku=None):
    r = {"msku": sku, "seller_sku": sku, "asin": "B0" + sku.replace("-", "")[:8].ljust(8, "0"), "fnsku": fnsku or "X0" + sku[-6:],
         "item_name": "Dog Toy", "brand": "DemoBrand", "sid": 9001, "status": 1,
         "price": price, "listing_price": price, "currency_code": "USD"}
    if regular is not None:
        r["regular_price"] = regular
    return r


def _sync(rows):
    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    res = sched.run_once(client_factory=_factory(rows), sleep=lambda s: None)
    assert res["ok"], res
    return res


def _customs(sku):
    from fba_tool.customs_package import build_customs_from_tickets

    line = {"sku": sku, "qty": 2, "chinese_name": "宠物垫", "hs_code": "6307909000", "unit": "包", "category": "pet"}
    return build_customs_from_tickets([{"shipment_id": "FBA1", "warehouse": "SBD1", "boxes": [5], "lines": [line]}],
                                      PROFILE, order_no="JUS1")


def _promo_warning(data):
    return [w for w in data.warnings if w["code"] == "promo_price_not_used"]


def test_row_to_dict_returns_d12_columns(env):
    _sync([_row("P-20OFF", 15.99, 19.99)])
    db = sqlite3.connect(env / "fba_master.db").execute(
        "SELECT regular_price, listing_price FROM product_master WHERE sku='P-20OFF'").fetchone()
    assert db == (19.99, 15.99)
    p = get_product_by_sku("P-20OFF")
    for k in ("regular_price", "regular_price_at", "last_nonpromo_price", "last_nonpromo_at"):
        assert k in p
    assert p["regular_price"] == pytest.approx(19.99) and p["regular_price_at"]
    assert lookup_by_fnsku(p["fnsku"])["regular_price"] == pytest.approx(19.99)


def test_e2e_20pct_promo_declares_regular_and_warns(env):
    _sync([_row("P-20OFF", 15.99, 19.99)])
    p = get_product_by_sku("P-20OFF")
    assert resolve_declared_price(p) == (pytest.approx(19.99), "lingxing_regular")
    assert promo_info(p)["drop_pct"] == 20.0
    data = _customs("P-20OFF")
    assert data.lines[0].unit_price == pytest.approx(19.99)
    w = _promo_warning(data)
    assert len(w) == 1 and "15.99" in w[0]["message"] and "19.99" in w[0]["message"]


def test_e2e_invoice_price_rows_promo(env):
    from fba_tool.invoice_rules import price_rows

    _sync([_row("P-20OFF", 15.99, 19.99, fnsku="X0PROMO01")])
    p = lookup_by_fnsku("X0PROMO01")
    r = price_rows({"X0PROMO01": p}, ["X0PROMO01"])[0]
    assert (r["unit_price"], r["price_source"], r["promo_price"]) == (pytest.approx(19.99), "lingxing_regular", pytest.approx(15.99))


def test_e2e_5_1pct_promo(env):
    _sync([_row("P-5-1", 18.98, 20.0)])
    p = get_product_by_sku("P-5-1")
    assert resolve_declared_price(p) == (pytest.approx(20.0), "lingxing_regular")
    assert _promo_warning(_customs("P-5-1"))


def test_e2e_exact_5pct_not_promo(env):
    _sync([_row("P-5-0", 19.0, 20.0)])
    p = get_product_by_sku("P-5-0")
    assert resolve_declared_price(p) == (pytest.approx(19.0), "lingxing")
    assert not _promo_warning(_customs("P-5-0"))


def test_e2e_no_regular_history_16_then_12(env):
    _sync([_row("P-NP", 16.0)])
    p = get_product_by_sku("P-NP")
    assert p["last_nonpromo_price"] == pytest.approx(16.0) and p["last_nonpromo_at"]
    assert resolve_declared_price(p) == (pytest.approx(16.0), "lingxing")
    _sync([_row("P-NP", 12.0)])
    p = get_product_by_sku("P-NP")
    assert p["listing_price"] == pytest.approx(12.0)
    assert p["last_nonpromo_price"] == pytest.approx(16.0)  # 促销价不覆盖“最近非促销价”
    assert resolve_declared_price(p) == (pytest.approx(16.0), "lingxing_recent_nonpromo")
    w = _promo_warning(_customs("P-NP"))
    assert w and "12.00" in w[0]["message"] and "16.00" in w[0]["message"]


def test_e2e_nonpromo_history_expires_after_90_days(env):
    _sync([_row("P-OLD", 16.0)])
    old = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
    con = sqlite3.connect(env / "fba_master.db")
    con.execute("UPDATE product_master SET last_nonpromo_at=? WHERE sku='P-OLD'", (old,))
    con.commit()
    con.close()
    _sync([_row("P-OLD", 12.0)])
    assert resolve_declared_price(get_product_by_sku("P-OLD")) == (pytest.approx(12.0), "lingxing")


def test_e2e_scheduled_auto_apply_path(env):
    """定时任务（trigger=scheduled，按预览默认勾选自动写入）同样带上常规价。"""
    res = _sync([_row("P-AUTO", 15.0, 20.0)])
    run = sqlite3.connect(env / "fba_master.db").execute(
        "SELECT status, trigger FROM lingxing_sync_run WHERE id=?", (res["run_id"],)).fetchone()
    assert run == ("auto_applied", "scheduled")
    p = get_product_by_sku("P-AUTO")
    assert resolve_declared_price(p) == (pytest.approx(20.0), "lingxing_regular")
    assert _promo_warning(_customs("P-AUTO"))


def test_e2e_manual_regular_price_patch_takes_effect(env):
    from fastapi.testclient import TestClient
    from main import app

    _sync([_row("P-MAN", 15.0)])
    c = TestClient(app)
    r = c.patch("/api/master-data/sku/P-MAN", json={"field": "regular_price", "value": 20})
    assert r.status_code == 200, r.text
    assert resolve_declared_price(get_product_by_sku("P-MAN")) == (pytest.approx(20.0), "lingxing_regular")


def test_e2e_manual_sync_preview_confirm_path(env):
    """手动同步 → 预览 → confirm：按预览默认勾选（售价 + 常规价）写入，申报价走 D-12（S8 评审 v2 补测）。
    S9-step2-fix A1：常规价是独立的可勾选价格字段，单独变化也会出现在预览里；只勾售价时不再顺带写常规价。"""
    from fastapi.testclient import TestClient
    from main import app

    _sync([_row("P-MSYNC", 15.0)])  # 先有这条产品，没有常规价
    assert resolve_declared_price(get_product_by_sku("P-MSYNC"))[1] != "lingxing_regular"
    list(ls.iter_full_sync_events(client=_factory([_row("P-MSYNC", 16.0, 20.0)])()))  # 手动同步（侧栏按钮走的流）
    run_id = sqlite3.connect(env / "fba_master.db").execute("SELECT MAX(id) FROM lingxing_sync_run").fetchone()[0]
    c = TestClient(app)
    prev = c.get("/api/lingxing/sync/preview", params={"run_id": run_id}).json()
    assert prev["pending"] is True
    items = [g for k in ("changed", "needs_review", "new") for g in prev["groups"].get(k, []) if g["sku"] == "P-MSYNC"]
    assert items and {"listing_price", "regular_price"} <= {f["field"] for f in items[0]["fields"]}
    assert get_product_by_sku("P-MSYNC").get("regular_price") in (None, "")  # 没确认前不写库
    r = c.post("/api/lingxing/sync/confirm", json={"run_id": run_id, "items": [{"sku": "P-MSYNC", "fields": ["listing_price", "regular_price"]}]})
    assert r.status_code == 200, r.text
    p = get_product_by_sku("P-MSYNC")
    assert p["regular_price"] == pytest.approx(20.0) and p["listing_price"] == pytest.approx(16.0)
    assert resolve_declared_price(p) == (pytest.approx(20.0), "lingxing_regular")
    assert _promo_warning(_customs("P-MSYNC"))
