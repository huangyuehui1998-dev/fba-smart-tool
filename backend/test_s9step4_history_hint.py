"""S9-step4：S9-B 提示（D-15，last_nonpromo_origin 三态）、领星常规价 90 天有效期（D-16）、人工确认正常价、
迁移（ADD COLUMN 带默认值、幂等、兼容旧版 exe）。mock 领星 + 临时 app_data，示例数据。"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from test_s5_lingxing_schedule import FAKE_KEY, _factory, env  # noqa: F401  (env 是 fixture)
from test_s8fix1_dec12_e2e import _row, _sync
from fba_tool import lingxing_sync as ls
from fba_tool.master_db import get_product_by_sku, init_master_db
from fba_tool.product_fields import (
    HISTORY_HINT_TEXT,
    ORIGIN_CONFIRMED,
    ORIGIN_LEGACY,
    ORIGIN_SELF_FIRST,
    confirm_normal_price,
    has_price_history,
    normal_price,
    price_history_hint,
    resolve_declared_price,
)

HINT = "无促销前历史价，申报价可能偏低，请人工确认"


def _ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _sql(env, sql, args=()):
    con = sqlite3.connect(env / "fba_master.db")
    con.execute(sql, args)
    con.commit()
    con.close()


def _diffs(env, kind):
    con = sqlite3.connect(env / "fba_master.db")
    run_id = con.execute("SELECT MAX(id) FROM lingxing_sync_run").fetchone()[0]
    rows = con.execute("SELECT sku, message FROM lingxing_sync_diff WHERE run_id=? AND kind=?", (run_id, kind)).fetchall()
    con.close()
    return rows


def _manual_preview(rows):
    from fba_tool.lingxing_preview import serialize_preview

    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    list(ls.iter_full_sync_events(client=_factory(rows)()))
    from fba_tool.master_db import _connect

    with _connect() as c:
        run_id = c.execute("SELECT MAX(id) FROM lingxing_sync_run").fetchone()[0]
    pv = serialize_preview(run_id)
    con_rows = {r["sku"]: r for g in pv["groups"].values() for r in g}
    return run_id, con_rows


def test_hint_text_exact_and_no_list_price():
    assert HISTORY_HINT_TEXT == HINT
    assert "list" not in HINT.lower() and "划线" not in HINT and "建议" not in HINT


# ---------------- 三态 origin ----------------
def test_first_sync_self_first_hint_in_preview_and_diff(env):
    _sync([_row("DEMO-H1", 16.0)])
    p = get_product_by_sku("DEMO-H1")
    assert p["last_nonpromo_origin"] == ORIGIN_SELF_FIRST and p["last_nonpromo_price"] == pytest.approx(16.0)
    assert not has_price_history(p) and price_history_hint(p) == HINT
    assert resolve_declared_price(p) == (16.0, "lingxing")  # 申报价不变
    assert ("DEMO-H1", HINT) in _diffs(env, "price_history_missing")


def test_new_sku_preview_shows_hint(env):
    _run, rows = _manual_preview([_row("DEMO-H2", 16.0)])
    info = rows["DEMO-H2"]["price_info"]
    assert info["history_hint"] == HINT
    assert ("DEMO-H2", HINT) in _diffs(env, "price_history_missing")


def test_later_sync_with_reference_confirms(env):
    _sync([_row("DEMO-H3", 16.0)])
    # S9-step4-fix3（D-15 修订）：self_first 不作为升级参照；这里先把记录改成 legacy（真参照），再同步才升 confirmed
    _sql(env, "UPDATE product_master SET last_nonpromo_origin='legacy' WHERE sku='DEMO-H3'")
    _sync([_row("DEMO-H3", 16.5)])
    p = get_product_by_sku("DEMO-H3")
    assert p["last_nonpromo_origin"] == ORIGIN_CONFIRMED and p["last_nonpromo_price"] == pytest.approx(16.5)
    assert price_history_hint(p) == "" and not _diffs(env, "price_history_missing")


def test_later_sync_self_first_only_reference_stays_self_first(env):
    _sync([_row("DEMO-H3B", 16.0)])
    _sync([_row("DEMO-H3B", 16.5)])  # 只有 self_first 可作参照 → 仍记 self_first，提示保留（D-15 修订）
    p = get_product_by_sku("DEMO-H3B")
    assert p["last_nonpromo_origin"] == ORIGIN_SELF_FIRST and p["last_nonpromo_price"] == pytest.approx(16.5)
    assert price_history_hint(p) == HINT and ("DEMO-H3B", HINT) in _diffs(env, "price_history_missing")


def test_unchanged_price_keeps_self_first(env):
    _sync([_row("DEMO-H4", 16.0)])
    _sync([_row("DEMO-H4", 16.0)])  # 价格没变：不写售价，不会记新记录，仍是 self_first，提示保留
    assert get_product_by_sku("DEMO-H4")["last_nonpromo_origin"] == ORIGIN_SELF_FIRST
    assert ("DEMO-H4", HINT) in _diffs(env, "price_history_missing")


def test_self_first_still_feeds_d12(env):
    _sync([_row("DEMO-H5", 16.0)])
    _sync([_row("DEMO-H5", 12.0)])  # 比 self_first 16 低 25% → 促销，按 16 报（D-12 不变），但仍提示
    p = get_product_by_sku("DEMO-H5")
    assert resolve_declared_price(p) == (16.0, "lingxing_recent_nonpromo")
    assert p["last_nonpromo_origin"] == ORIGIN_SELF_FIRST and price_history_hint(p) == HINT


def test_informative_regular_suppresses_hint(env):
    _sync([_row("DEMO-H6", 15.99, 19.99)])
    p = get_product_by_sku("DEMO-H6")
    assert price_history_hint(p) == ""
    assert not [s for s, _ in _diffs(env, "price_history_missing") if s == "DEMO-H6"]


def test_legacy_counts_as_history(env):
    _sync([_row("DEMO-H7", 16.0)])
    _sql(env, "UPDATE product_master SET last_nonpromo_origin='legacy' WHERE sku='DEMO-H7'")
    assert has_price_history(get_product_by_sku("DEMO-H7")) and price_history_hint(get_product_by_sku("DEMO-H7")) == ""
    _sql(env, "UPDATE product_master SET last_nonpromo_origin=NULL WHERE sku='DEMO-H7'")  # 空也按 legacy
    assert price_history_hint(get_product_by_sku("DEMO-H7")) == ""


def test_record_rolls_out_of_window_hint_returns(env):
    _sync([_row("DEMO-H8", 16.0)])
    _sql(env, "UPDATE product_master SET last_nonpromo_origin='confirmed', last_nonpromo_at=? WHERE sku='DEMO-H8'", (_ago(91),))
    assert price_history_hint(get_product_by_sku("DEMO-H8")) == HINT  # 促销超过 90 天，记录滚出窗口 → 提示回来
    _sync([_row("DEMO-H8", 12.0)])  # 没有参照 → 重新记 self_first
    assert get_product_by_sku("DEMO-H8")["last_nonpromo_origin"] == ORIGIN_SELF_FIRST


# ---------------- 人工确认 ----------------
def test_confirm_api_default_price_and_audit(env):
    from fastapi.testclient import TestClient
    from main import app

    _sync([_row("DEMO-C1", 16.0)])
    c = TestClient(app)
    r = c.post("/api/master-data/sku/demo-c1/confirm-normal-price", json={"price": "16.00"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sku"] == "DEMO-C1" and body["price"] == 16.0 and body["origin"] == "confirmed" and body["history_hint"] == ""
    p = get_product_by_sku("DEMO-C1")
    assert p["last_nonpromo_origin"] == ORIGIN_CONFIRMED and price_history_hint(p) == ""
    lines = (env / "logs" / "price_confirm_audit.log").read_text(encoding="utf-8").strip().splitlines()
    rec = json.loads(lines[-1])
    assert rec["action"] == "confirm_normal_price" and rec["sku"] == "DEMO-C1" and rec["price"] == 16.0
    assert rec["old_origin"] == ORIGIN_SELF_FIRST and rec["old_last_nonpromo_price"] == 16.0
    assert "key" not in json.dumps(rec).lower()


def test_confirm_edited_price_used_by_d12(env):
    _sync([_row("DEMO-C2", 12.0)])
    confirm_normal_price("DEMO-C2", "16")  # 用户确认正常价 16（比售价高 33%）→ 促销，按 16 报
    p = get_product_by_sku("DEMO-C2")
    assert normal_price(p) == (16.0, "lingxing_recent_nonpromo") and resolve_declared_price(p)[0] == 16.0


@pytest.mark.parametrize("bad,code", [("12,5", 422), ("0", 422), ("200000", 422), ("", 422), ("1e3", 422)])
def test_confirm_api_validation(env, bad, code):
    from fastapi.testclient import TestClient
    from main import app

    _sync([_row("DEMO-C3", 16.0)])
    r = TestClient(app).post("/api/master-data/sku/DEMO-C3/confirm-normal-price", json={"price": bad})
    assert r.status_code == code, r.text
    assert get_product_by_sku("DEMO-C3")["last_nonpromo_origin"] == ORIGIN_SELF_FIRST


def test_confirm_api_unknown_and_conflict(env):
    from fastapi.testclient import TestClient
    from main import app

    c = TestClient(app)
    assert c.post("/api/master-data/sku/DEMO-NONE/confirm-normal-price", json={"price": 10}).status_code == 404
    for s in ("DEMO-CF", "demo-cf"):
        _sql(env, "INSERT INTO product_master (sku, updated_at) VALUES (?, '2026-01-01T00:00:00+00:00')", (s,))
    assert c.post("/api/master-data/sku/Demo-Cf/confirm-normal-price", json={"price": 10}).status_code == 409


def test_confirm_price_max_from_settings(env, monkeypatch):
    import fba_tool.user_config as uc

    _sync([_row("DEMO-C4", 16.0)])
    monkeypatch.setattr(uc, "param", lambda k, d=None: 20 if k == "price_max" else d)
    with pytest.raises(ValueError):
        confirm_normal_price("DEMO-C4", 25)
    assert confirm_normal_price("DEMO-C4", 19.995)["price"] == 20.0  # HALF_UP 到 20.00，不超过上限


def test_preview_hint_disappears_after_confirm(env):
    _sync([_row("DEMO-C5", 16.0)])
    run_id, rows = _manual_preview([_row("DEMO-C5", 16.0), _row("DEMO-C5B", 9.0)])
    assert rows["DEMO-C5"]["price_info"]["history_hint"] == HINT
    confirm_normal_price("DEMO-C5", rows["DEMO-C5"]["price_info"]["declared_price"])
    from fba_tool.lingxing_preview import serialize_preview

    again = {r["sku"]: r for g in serialize_preview(run_id)["groups"].values() for r in g}
    assert again["DEMO-C5"]["price_info"]["history_hint"] == ""


# ---------------- 领星常规价 90 天有效期（D-16） ----------------
def test_regular_price_window(env):
    _sync([_row("DEMO-R1", 15.99, 19.99)])
    _sql(env, "UPDATE product_master SET regular_price_at=? WHERE sku='DEMO-R1'", (_ago(89),))
    assert normal_price(get_product_by_sku("DEMO-R1")) == (19.99, "lingxing_regular")
    _sql(env, "UPDATE product_master SET regular_price_at=? WHERE sku='DEMO-R1'", (_ago(91),))
    p = get_product_by_sku("DEMO-R1")
    # 首次同步时 15.99 比常规价 19.99 低 20%（促销），没有记非促销价；常规价超期 → 当作没有常规价，也没有历史 → 无正常价
    assert normal_price(p) == (None, "")
    assert resolve_declared_price(p) == (15.99, "lingxing")
    assert price_history_hint(p) == HINT
    _sql(env, "UPDATE product_master SET last_nonpromo_price=17.5, last_nonpromo_at=?, last_nonpromo_origin='confirmed' "
              "WHERE sku='DEMO-R1'", (_ago(5),))
    p = get_product_by_sku("DEMO-R1")
    assert normal_price(p) == (17.5, "lingxing_recent_nonpromo") and price_history_hint(p) == ""  # 超期后回退历史


def test_preview_shows_regular_capture_date_and_expired(env):
    _sync([_row("DEMO-R2", 15.99, 19.99)])
    _sql(env, "UPDATE product_master SET regular_price_at=? WHERE sku='DEMO-R2'", ("2026-01-02T03:04:05+00:00",))
    _run, rows = _manual_preview([_row("DEMO-R2", 15.49)])  # 领星这次没给常规价 → 用本地旧值
    info = rows["DEMO-R2"]["price_info"]
    assert info["regular_price_origin"] == "local" and info["regular_price_at"] == "2026-01-02"
    assert info["regular_price_expired"] is True and info["regular_price_informative"] is False
    assert info["declared_source"] != "lingxing_regular"


def test_regular_written_now_not_expired(env):
    _sync([_row("DEMO-R3", 15.99, 15.99)])
    _sql(env, "UPDATE product_master SET regular_price_at=? WHERE sku='DEMO-R3'", (_ago(200),))
    _run, rows = _manual_preview([_row("DEMO-R3", 15.99, 19.99)])
    info = rows["DEMO-R3"]["price_info"]
    assert info["regular_price_origin"] == "remote" and info["regular_price_expired"] is False
    assert info["declared_source"] == "lingxing_regular"


# ---------------- 迁移：ADD COLUMN 默认值、幂等、兼容旧版 exe ----------------
def _old_schema(env):
    """把临时库改成旧结构（没有 last_nonpromo_origin），模拟升级前的库。"""
    if sqlite3.sqlite_version_info < (3, 35, 0):
        pytest.skip("SQLite < 3.35 不支持 DROP COLUMN")
    _sql(env, "ALTER TABLE product_master DROP COLUMN last_nonpromo_origin")


def test_migration_old_schema_upgrade(env):
    _old_schema(env)
    con = sqlite3.connect(env / "fba_master.db")
    cols = {r[1] for r in con.execute("PRAGMA table_info(product_master)")}
    assert "last_nonpromo_origin" not in cols
    con.execute("INSERT INTO product_master (sku, listing_price, regular_price, regular_price_at, last_nonpromo_price, "
                "last_nonpromo_at, updated_at) VALUES ('DEMO-OLD1', 15.99, 19.99, NULL, 16.0, ?, '2026-01-01')", (_ago(10),))
    con.execute("INSERT INTO product_master (sku, listing_price, regular_price, regular_price_at, updated_at) "
                "VALUES ('DEMO-OLD2', 9.0, 9.5, '2026-01-02T00:00:00+00:00', '2026-01-01')")
    con.commit()
    con.close()
    init_master_db()  # 升级
    p1, p2 = get_product_by_sku("DEMO-OLD1"), get_product_by_sku("DEMO-OLD2")
    assert p1["last_nonpromo_origin"] == ORIGIN_LEGACY and has_price_history(p1) and price_history_hint(p1) == ""
    at1 = p1["regular_price_at"]
    assert at1 and (datetime.now(timezone.utc) - datetime.fromisoformat(at1)).total_seconds() < 120  # 没时间的用迁移时间
    assert p2["regular_price_at"] == "2026-01-02T00:00:00+00:00"  # 有时间的不动
    assert normal_price(p1) == (19.99, "lingxing_regular")
    init_master_db()  # 幂等：再跑一次不报错、不改已补的时间
    assert get_product_by_sku("DEMO-OLD1")["regular_price_at"] == at1
    con = sqlite3.connect(env / "fba_master.db")
    assert [r[1] for r in con.execute("PRAGMA table_info(product_master)")].count("last_nonpromo_origin") == 1
    # 旧版 exe 不认识新列：照旧 INSERT / UPDATE / SELECT * 都能用，新列取默认 legacy
    con.execute("INSERT INTO product_master (sku, listing_price, last_nonpromo_price, last_nonpromo_at, updated_at) "
                "VALUES ('DEMO-OLDEXE', 20.0, 20.0, ?, '2026-01-01')", (_ago(1),))
    con.execute("UPDATE product_master SET last_nonpromo_price = 21.0 WHERE sku = 'DEMO-OLDEXE'")
    con.commit()
    row = con.execute("SELECT * FROM product_master WHERE sku='DEMO-OLDEXE'").fetchone()
    con.close()
    assert row is not None
    assert get_product_by_sku("DEMO-OLDEXE")["last_nonpromo_origin"] == ORIGIN_LEGACY
