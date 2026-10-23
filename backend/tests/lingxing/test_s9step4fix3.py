"""S9-step4-fix3：护栏按内容比对（9 种复制方式）、SKU 键不再用 upper（发票同票只差大小写不互相覆盖）、
S9-B self_first 不作为升级参照（D-15 修订）、FBA_NO_BROWSER 不再关打包版迁移、冲突 409、90 天窗口分钟级边界、
审计截断、全坏行 422 带行号。全部用 tmp_path 里的示例数据（DEMO-*），不碰真实数据。"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

import realdata_guard as rg
from fba_tool import app_paths
from test_s5_lingxing_schedule import env  # noqa: F401  (fixture)
from test_s8fix1_dec12_e2e import _row, _sync

HINT = "无促销前历史价，申报价可能偏低，请人工确认"
BACKEND = Path(__file__).resolve().parents[2]


# ======================= 1. 护栏：按内容比对 =======================

def _fake_real(root: Path) -> Path:
    """造一份“真实来源”（示例）：带 product_master 的 SQLite 库 + 两个会话文件。"""
    (root / "config" / "sessions" / "history").mkdir(parents=True)
    con = sqlite3.connect(root / "fba_master.db")
    con.execute("CREATE TABLE product_master (sku TEXT PRIMARY KEY, asin TEXT, updated_at TEXT NOT NULL)")
    con.executemany("INSERT INTO product_master VALUES (?, ?, ?)",
                    [(f"DEMO-REAL-{i}", f"B0DEMO{i:04d}", f"2026-05-30T10:{i:02d}:48.123456+00:00") for i in range(5)])
    con.commit()
    con.close()
    (root / "config" / "sessions" / "autosave.json").write_text(json.dumps({"task_id": "demo-real", "box": list(range(50))}), encoding="utf-8")
    (root / "config" / "sessions" / "history" / "demo.json").write_text(json.dumps({"task_id": "demo-hist", "rows": ["x"] * 30}), encoding="utf-8")
    return root


def _plain_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)  # 不保留 mtime


def _stream_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(src, "rb") as a, open(dst, "wb") as b:
        while True:
            chunk = a.read(7)
            if not chunk:
                break
            b.write(chunk)


def _copy2(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


DB = "fba_master.db"
SESS = "config/sessions/autosave.json"
METHODS = [
    ("copy2_same_name_db", DB, "fba_master.db", _copy2),
    ("copy2_into_sessions_renamed", SESS, "sessions/renamed.json", _copy2),
    ("copy2_db_renamed", DB, "old_master.db", _copy2),
    ("copy2_db_to_config_backup", DB, "config/backup.sqlite", _copy2),
    ("copyfile_same_name_db", DB, "fba_master.db", _plain_copy),
    ("copyfile_same_name_into_sessions", SESS, "sessions/autosave.json", _plain_copy),
    ("copyfile_renamed_into_sessions", SESS, "sessions/history/zz.json", _plain_copy),
    ("copy2_session_outside_sessions", SESS, "cache/some.json", _copy2),
    ("stream_copy_renamed_db", DB, "x/y/data.bin", _stream_copy),
]


@pytest.mark.parametrize("name,src,dst,how", METHODS, ids=[m[0] for m in METHODS])
def test_guard_catches_copy_methods(tmp_path, name, src, dst, how):
    real = _fake_real(tmp_path / "real")
    idx = rg.RealDataIndex(rg.real_sources(real, tmp_path / "noroot"))
    ad = tmp_path / "ad"
    ad.mkdir()
    assert idx.find_copies(ad) == []
    how(real / src, ad / dst)
    found = idx.find_copies(ad)
    assert [f.split(":")[0] for f in found] == [dst], found
    os.remove(ad / dst)


def test_guard_catches_db_rewritten_by_init(tmp_path, monkeypatch):
    """第 9 种：复制后被 init_master_db 改写（加列、补字段，大小和 mtime 都变了）→ 靠 SQLite 表特征认出来。"""
    from fba_tool import master_db

    real = tmp_path / "real"
    (real / "config" / "sessions").mkdir(parents=True)
    monkeypatch.setattr(master_db, "_master_db_file", lambda: real / DB)
    master_db.init_master_db()  # 真实库用当前表结构（示例数据），行的 updated_at 是固定的旧时间
    con = sqlite3.connect(real / DB)
    con.executemany("INSERT INTO product_master (sku, asin, updated_at) VALUES (?, ?, ?)",
                    [(f"DEMO-REAL-{i}", f"B0DEMO{i:04d}", f"2026-05-30T10:{i:02d}:48.123456+00:00") for i in range(5)])
    con.commit()
    con.close()
    idx = rg.RealDataIndex(rg.real_sources(real, tmp_path / "noroot"))
    ad = tmp_path / "ad"
    ad.mkdir()
    shutil.copyfile(real / DB, ad / DB)
    before = (ad / DB).read_bytes()
    monkeypatch.setattr(master_db, "_master_db_file", lambda: ad / DB)
    master_db.init_master_db()  # 复制后被初始化 + 写入改写
    master_db.upsert_product({"sku": "DEMO-NEW-1", "asin": "B0DEMONEW1"})
    assert (ad / DB).read_bytes() != before
    found = idx.find_copies(ad)
    assert len(found) == 1 and found[0].startswith("fba_master.db:") and "product_master" in found[0]
    os.remove(ad / DB)


def test_guard_no_false_positive_on_test_built_db_and_files(tmp_path, monkeypatch):
    from fba_tool import master_db

    real = _fake_real(tmp_path / "real")
    idx = rg.RealDataIndex(rg.real_sources(real, tmp_path / "noroot"))
    ad = tmp_path / "ad"
    (ad / "sessions").mkdir(parents=True)
    monkeypatch.setattr(master_db, "_master_db_file", lambda: ad / DB)
    master_db.init_master_db()
    master_db.upsert_product({"sku": "DEMO-REAL-1", "asin": "B0DEMO0001"})  # 同名 SKU，但行是测试写的
    same_size = (real / SESS).read_bytes().replace(b"demo-real", b"demo-fake")
    assert len(same_size) == (real / SESS).stat().st_size
    (ad / "sessions" / "autosave.json").write_bytes(same_size)  # 同大小、内容不同
    assert idx.find_copies(ad) == []


def test_guard_output_has_no_digest_or_source_path(tmp_path):
    real = _fake_real(tmp_path / "real_secret_dir")
    idx = rg.RealDataIndex(rg.real_sources(real, tmp_path / "noroot"))
    ad = tmp_path / "ad"
    _copy2(real / DB, ad / "a.db")
    msg = "\n".join(idx.find_copies(ad))
    assert msg and "real_secret_dir" not in msg and not re.search(r"[0-9a-f]{32,}", msg)
    os.remove(ad / "a.db")


def test_guard_caches_unchanged_files(tmp_path, monkeypatch):
    real = _fake_real(tmp_path / "real")
    idx = rg.RealDataIndex(rg.real_sources(real, tmp_path / "noroot"))
    ad = tmp_path / "ad"
    (ad / "sessions").mkdir(parents=True)
    (ad / "sessions" / "s.json").write_bytes(b"x" * (real / SESS).stat().st_size)  # 同大小 → 要算哈希
    calls = []
    orig = rg._sha256
    monkeypatch.setattr(rg, "_sha256", lambda p: calls.append(p) or orig(p))
    idx.find_copies(ad)
    idx.find_copies(ad)
    assert len(calls) == 1  # 没变的文件第二次不再读


def test_conftest_index_covers_real_sources():
    import conftest

    srcs = rg.real_sources(BACKEND, BACKEND.parent)
    assert conftest._real_index().count == len([p for p in srcs if p.is_file()])
    assert conftest._real_index().find_copies(os.environ["FBA_APP_DATA_DIR"]) == []


# ======================= 2. 迁移判断：FBA_NO_BROWSER 不再影响 =======================

def test_no_browser_does_not_block_frozen_migration(tmp_path, monkeypatch):
    exe_dir = tmp_path / "portable"
    (exe_dir / "config" / "sessions").mkdir(parents=True)
    (exe_dir / "fba_master.db").write_bytes(b"FAKE-LEGACY-DB")
    (exe_dir / "config" / "sessions" / "autosave.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "FBA_Smart_Tool.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(BACKEND), raising=False)
    monkeypatch.delenv("FBA_APP_DATA_DIR", raising=False)
    monkeypatch.delenv(app_paths.LEGACY_MIGRATION_ENV, raising=False)
    monkeypatch.setenv("FBA_NO_BROWSER", "1")
    monkeypatch.setattr(app_paths, "_in_test_env", lambda: False)
    assert app_paths.legacy_migration_decision() == (True, "frozen")
    ad = app_paths.ensure_app_data_layout()
    assert (ad / "fba_master.db").read_bytes() == b"FAKE-LEGACY-DB" and (ad / "sessions" / "autosave.json").is_file()


def test_in_test_env_ignores_no_browser(monkeypatch):
    monkeypatch.setenv("FBA_NO_BROWSER", "1")
    monkeypatch.delitem(sys.modules, "pytest")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert app_paths._in_test_env() is False


def test_dev_mode_no_browser_still_default_off(monkeypatch):
    monkeypatch.setenv("FBA_NO_BROWSER", "1")
    monkeypatch.delenv("FBA_APP_DATA_DIR", raising=False)
    monkeypatch.delenv(app_paths.LEGACY_MIGRATION_ENV, raising=False)
    monkeypatch.setattr(app_paths, "_in_test_env", lambda: False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert app_paths.legacy_migration_decision() == (False, "dev_default")


# ======================= 3. SKU：不再拿 upper() 当键 =======================

def _two_case_rows(env):
    con = sqlite3.connect(env / "fba_master.db")
    for sku, cn, hs in (("DEMO-K2", "甲品名", "1111111111"), ("demo-k2", "乙品名", "2222222222")):
        con.execute("INSERT INTO product_master (sku, chinese_name, hs_code, english_name, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (sku, cn, hs, f"EN {cn}", "2026-01-01T00:00:00+00:00"))
    con.commit()
    con.close()


def _ship(skus):
    from fba_tool.shipment_parser import CsvShipment

    n = len(skus)
    return CsvShipment(
        shipment_id="FBA0DEMO0001", warehouse_code="DEMO1", box_count=n,
        box_items=pd.DataFrame({"箱号": list(range(1, n + 1)), "SKU": skus, "数量": [10] * n}),
        box_specs=pd.DataFrame({"箱号": list(range(1, n + 1)), "长(cm)": [30] * n, "宽(cm)": [20] * n,
                                "高(cm)": [10] * n, "实重(kg)": [5.0] * n}),
    )


def _csv(rows):
    return ("SKU,商品名称,ASIN,FNSKU\n" + "".join(f"{s},{t},{a},{f}\n" for s, t, a, f in rows)).encode("utf-8")


def test_csv_sku_meta_keeps_original_case():
    from fba_tool.invoice_table import extract_csv_sku_meta
    from fba_tool.sku_keys import lookup_sku

    meta = extract_csv_sku_meta(_csv([("DEMO-K2", "Title Upper", "B0DEMOUP01", "X0DEMOUP01"),
                                      ("demo-k2", "Title Lower", "B0DEMOLO01", "X0DEMOLO01")]))
    assert set(meta) == {"DEMO-K2", "demo-k2"}
    assert lookup_sku(meta, "DEMO-K2")["title"] == "Title Upper" and lookup_sku(meta, "demo-k2")["title"] == "Title Lower"
    assert lookup_sku(meta, "Demo-K2") is None  # 只差大小写的两个候选：不任选


def test_customs_by_sku_two_case_skus_not_overwritten(env, monkeypatch):
    from fba_tool import invoice_automation as ia

    _two_case_rows(env)
    monkeypatch.setattr(ia, "extract_csv_skus", lambda b: ["DEMO-K2", "demo-k2"])
    res, _ai = ia._customs_by_sku(_csv([("DEMO-K2", "T1", "", ""), ("demo-k2", "T2", "", "")]), None, None)
    assert set(res) == {"DEMO-K2", "demo-k2"}
    assert res["DEMO-K2"]["海关编码"] == "1111111111" and res["DEMO-K2"]["中文品名"] == "甲品名"
    assert res["demo-k2"]["海关编码"] == "2222222222" and res["demo-k2"]["中文品名"] == "乙品名"


def test_invoice_lines_two_case_skus_each_correct(env, monkeypatch):
    from fba_tool import invoice_automation as ia
    from fba_tool.invoice_table import build_invoice_line_items

    _two_case_rows(env)
    csv_bytes = _csv([("DEMO-K2", "T1", "", ""), ("demo-k2", "T2", "", "")])
    monkeypatch.setattr(ia, "extract_csv_skus", lambda b: ["DEMO-K2", "demo-k2"])
    customs, ai_keys = ia._customs_by_sku(csv_bytes, None, None)
    items = build_invoice_line_items(_ship(["DEMO-K2", "demo-k2"]), csv_bytes, None, customs_by_sku=customs, customs_ai_keys=ai_keys)
    by = {it.values["sku"]: it.values for it in items}
    assert by["DEMO-K2"]["hs_code"] == "1111111111" and by["demo-k2"]["hs_code"] == "2222222222"
    # 英文品名以各自产品库为准，不再用货件标题 T1/T2 盖掉。
    assert by["DEMO-K2"]["english_name"] == "EN 甲品名" and by["demo-k2"]["english_name"] == "EN 乙品名"


def test_invoice_case_conflict_warning():
    from fba_tool.invoice_automation import _sku_case_warnings

    w = _sku_case_warnings(_ship(["DEMO-K2", "demo-k2", "DEMO-OTHER"]))
    assert len(w) == 1 and "DEMO-K2、demo-k2" in w[0] and "没有合并" in w[0]
    assert _sku_case_warnings(_ship(["DEMO-A", "DEMO-B"])) == []


def test_workflow_bundle_case():
    from fba_tool.invoice_workflow_fill import build_workflow_bundle
    from fba_tool.sku_keys import lookup_sku

    b = build_workflow_bundle({"input_rows": [{"SKU简称": "DEMO-W1", "单箱装量": 4}],
                               "forwarder": [{"SKU": "demo-w1", "箱序号": "1,2"}]})
    assert list(b.by_sku) == ["DEMO-W1"] and b.by_sku["DEMO-W1"].box_seq == "1-2"  # 唯一规范命中：并到同一条
    b2 = build_workflow_bundle({"input_rows": [{"SKU简称": "DEMO-W2", "单箱装量": 4}, {"SKU简称": "demo-w2", "单箱装量": 6}]})
    assert {k: v.per_box for k, v in b2.by_sku.items()} == {"DEMO-W2": 4, "demo-w2": 6}
    assert lookup_sku(b2.by_sku, "Demo-W2") is None


def test_editor_rows_match_exact_first():
    from fba_tool.invoice_workflow_fill import _boxes_from_editor

    ed = [{"SKU简称": "DEMO-E1", "箱号": 1}, {"SKU简称": "demo-e1", "箱号": 2}, {"SKU简称": "DEMO-E2", "箱号": 3}]
    assert _boxes_from_editor(ed, "DEMO-E1") == [1] and _boxes_from_editor(ed, "demo-e1") == [2]
    assert _boxes_from_editor(ed, "Demo-E1") == []  # 两个候选不任选
    assert _boxes_from_editor(ed, "demo-e2") == [3]  # 唯一规范命中


def test_step1_weight_map_original_keys():
    from fba_tool.customs_package import _weight_map_from_step1
    from fba_tool.sku_keys import lookup_sku

    m = _weight_map_from_step1([{"SKU": "DEMO-G1", "单个重量(kg)": 0.5}, {"SKU": "demo-g1", "单个重量(kg)": 0.7}])
    assert m == {"DEMO-G1": 0.5, "demo-g1": 0.7}
    assert lookup_sku(m, "DEMO-G1") == 0.5 and lookup_sku(m, "demo-g1") == 0.7


def test_product_catalog_keeps_case_and_matches(tmp_path):
    from fba_tool.product_catalog import parse_catalog

    p = tmp_path / "产品信息表.csv"
    p.write_text("序号,产品名称,SKU,ASIN\n1,Upper,DEMO-C1,B0DEMO0C1A\n2,Lower,demo-c1,B0DEMO0C1B\n3,Only,demo-c2,B0DEMO0C2A\n",
                 encoding="utf-8")
    cat = parse_catalog(p)
    assert set(cat.records) == {"DEMO-C1", "demo-c1", "demo-c2"}
    assert cat.lookup_with_match("DEMO-C1")[0].product_name == "Upper"
    assert cat.lookup_with_match("demo-c1")[0].product_name == "Lower"
    assert cat.lookup_with_match("Demo-C1") == (None, "ambiguous")
    rec, how = cat.lookup_with_match("DEMO-C2")
    assert rec.product_name == "Only" and rec.sku == "demo-c2" and how == "exact"


def test_catalog_seed_skips_conflicts(env, monkeypatch):
    from fba_tool import catalog_seed
    from fba_tool.product_catalog import ProductCatalog, ProductRecord

    _two_case_rows(env)
    cat = ProductCatalog(source_path=Path("x.csv"), records={
        "Demo-K2": ProductRecord(sku="Demo-K2", asin="B0DEMOK2XX"), "DEMO-NEW": ProductRecord(sku="DEMO-NEW", asin="B0DEMONEW1")})
    monkeypatch.setattr(catalog_seed, "load_product_catalog", lambda: cat)
    out = catalog_seed.import_catalog_gaps_into_master()
    from fba_tool.master_db import get_product_by_sku

    assert out["touched"] == 1 and get_product_by_sku("DEMO-NEW")["asin"] == "B0DEMONEW1"
    assert get_product_by_sku("DEMO-K2")["asin"] in (None, "")


# ======================= 4. 冲突统一 409 =======================

def test_patch_conflict_is_409_and_unknown_404(env):
    from fastapi.testclient import TestClient
    from main import app

    _two_case_rows(env)
    c = TestClient(app)
    r = c.patch("/api/master-data/sku/Demo-K2", json={"field": "chinese_name", "value": "丙"})
    assert r.status_code == 409, r.text
    assert c.patch("/api/master-data/sku/DEMO-NOPE", json={"field": "chinese_name", "value": "丙"}).status_code == 404
    r = c.patch("/api/master-data/sku/DEMO-K2", json={"field": "chinese_name", "value": "丙"})
    assert r.status_code == 200, r.text


def test_local_excel_sync_conflict_is_409_and_writes_nothing(env, monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    from fba_tool import master_local_excel as mle
    from fba_tool.master_db import get_product_by_sku

    _two_case_rows(env)
    path = env / mle.LOCAL_EXCEL_FILENAME
    monkeypatch.setattr(mle, "local_excel_path", lambda: path)  # 固定到本测试的临时目录（与其它测试的顺序无关）
    pd.DataFrame([{"SKU": "DEMO-OK1", "商品报关名称": "好"}, {"SKU": "Demo-K2", "商品报关名称": "丙"}]).to_excel(
        path, index=False, sheet_name=mle.SHEET_NAME)
    r = TestClient(app).post("/api/master-data/local-excel/sync")
    assert r.status_code == 409, r.text
    assert "整批没有同步" in r.json()["detail"]
    assert get_product_by_sku("DEMO-OK1") is None


# ======================= 5. S9-B：self_first 不作为升级参照 =======================

def _p(sku):
    from fba_tool.master_db import get_product_by_sku

    return get_product_by_sku(sku)


def _set(env, sql, args=()):
    con = sqlite3.connect(env / "fba_master.db")
    con.execute(sql, args)
    con.commit()
    con.close()


def test_consecutive_promo_prices_keep_hint(env):
    from fba_tool.product_fields import ORIGIN_SELF_FIRST, price_history_hint, resolve_declared_price

    for price in (16.0, 15.5, 17.0):
        _sync([_row("DEMO-N2", price)])
        p = _p("DEMO-N2")
        assert p["last_nonpromo_origin"] == ORIGIN_SELF_FIRST, price
        assert price_history_hint(p) == HINT, price
    assert p["last_nonpromo_price"] == pytest.approx(17.0)
    assert resolve_declared_price(p) == (17.0, "lingxing")  # 申报价算法不变


@pytest.mark.parametrize("second", [15.9, 15.5, 16.2, 16.5, 17.0])
def test_second_sync_small_change_keeps_hint(env, second):
    from fba_tool.product_fields import ORIGIN_SELF_FIRST, price_history_hint

    _sync([_row("DEMO-N2B", 16.0)])
    _sync([_row("DEMO-N2B", second)])
    p = _p("DEMO-N2B")
    assert p["last_nonpromo_origin"] == ORIGIN_SELF_FIRST and price_history_hint(p) == HINT


def test_self_first_promo_drop_still_declares_by_record(env):
    from fba_tool.product_fields import ORIGIN_SELF_FIRST, resolve_declared_price

    _sync([_row("DEMO-N2C", 16.0)])
    _sync([_row("DEMO-N2C", 12.0)])  # D-12 照旧：低 25% → 按 16 报
    p = _p("DEMO-N2C")
    assert resolve_declared_price(p) == (16.0, "lingxing_recent_nonpromo") and p["last_nonpromo_origin"] == ORIGIN_SELF_FIRST


def test_regular_price_reference_upgrades(env):
    from fba_tool.product_fields import ORIGIN_CONFIRMED, price_history_hint

    _sync([_row("DEMO-N2D", 16.0)])
    _sync([_row("DEMO-N2D", 16.5, 16.9)])  # 本次有有效领星常规价（高于售价）→ 真参照 → confirmed
    p = _p("DEMO-N2D")
    assert p["last_nonpromo_origin"] == ORIGIN_CONFIRMED and price_history_hint(p) == ""


@pytest.mark.parametrize("origin", ["confirmed", "legacy"])
def test_trusted_record_reference_upgrades(env, origin):
    from fba_tool.product_fields import ORIGIN_CONFIRMED

    _sync([_row("DEMO-N2E", 16.0)])
    _set(env, "UPDATE product_master SET last_nonpromo_origin=? WHERE sku='DEMO-N2E'", (origin,))
    _sync([_row("DEMO-N2E", 16.4)])
    assert _p("DEMO-N2E")["last_nonpromo_origin"] == ORIGIN_CONFIRMED


def test_confirm_after_self_first_chain_clears_hint(env):
    from fba_tool.product_fields import confirm_normal_price, price_history_hint

    _sync([_row("DEMO-N2F", 16.0)])
    _sync([_row("DEMO-N2F", 15.5)])
    confirm_normal_price("DEMO-N2F", "16.00")
    assert price_history_hint(_p("DEMO-N2F")) == ""


# ======================= 6. 90 天窗口：分钟级边界 =======================

def _ago(days=0, minutes=0):
    return (datetime.now(timezone.utc) - timedelta(days=days, minutes=minutes)).isoformat()


@pytest.mark.parametrize("delta_min,inside", [(-5, True), (-1, True), (1, False), (5, False)])
def test_window_minute_boundary(delta_min, inside):
    from fba_tool.product_fields import _in_window, regular_price_in_window

    at = _ago(days=90, minutes=delta_min)  # 90 天减 / 加几分钟
    assert _in_window(at) is inside
    assert regular_price_in_window({"regular_price": 20.0, "regular_price_at": at}) is inside


@pytest.mark.parametrize("delta_min,hint", [(-5, ""), (5, HINT)])
def test_window_boundary_drives_hint(env, delta_min, hint):
    from fba_tool.product_fields import price_history_hint

    _sync([_row("DEMO-W9", 16.0)])
    _set(env, "UPDATE product_master SET last_nonpromo_origin='confirmed', last_nonpromo_at=? WHERE sku='DEMO-W9'",
         (_ago(days=90, minutes=delta_min),))
    assert price_history_hint(_p("DEMO-W9")) == hint


def test_window_exact_90_days_is_inside(monkeypatch):
    from fba_tool import product_fields

    now = datetime.now(timezone.utc)
    monkeypatch.setattr(product_fields, "_utcnow", lambda: now)  # S9-step5 N7：固定当前时间，正好 90 天（不再留运行余量）
    assert product_fields._in_window((now - timedelta(days=90)).isoformat()) is True


def test_empty_capture_time_counts_as_fresh():
    from fba_tool.product_fields import regular_price_in_window

    assert regular_price_in_window({"regular_price": 20.0, "regular_price_at": ""}) is True
    assert regular_price_in_window({"regular_price": 20.0, "regular_price_at": None}) is True
    assert regular_price_in_window({"regular_price": None, "regular_price_at": _ago()}) is False


# ======================= 7. 审计日志截断 =======================

def test_audit_truncates_note_and_input(env):
    from fba_tool.product_fields import confirm_normal_price

    _sync([_row("DEMO-AU", 16.0)])
    raw = "16.50" + "0" * 50
    confirm_normal_price("DEMO-AU", raw, note="备" * 250)
    rec = json.loads((env / "logs" / "price_confirm_audit.log").read_text(encoding="utf-8").strip().splitlines()[-1])
    assert rec["input"] == raw[:40] and len(rec["input"]) == 40
    assert rec["note"] == "备" * 200
    assert rec["price"] == 16.5


def test_invalid_price_message_truncates_input(env):
    from fba_tool.product_fields import confirm_normal_price

    _sync([_row("DEMO-AU2", 16.0)])
    with pytest.raises(ValueError) as ei:
        confirm_normal_price("DEMO-AU2", "x" * 100)
    assert "x" * 40 in str(ei.value) and "x" * 41 not in str(ei.value)


# ======================= 8. 全坏行 422 带行号 =======================

def _listing_csv(rows):
    import csv

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["MSKU", "FNSKU", "ASIN", "价格"])
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8-sig")


def test_listing_all_bad_422_lists_rows(env):
    from fastapi.testclient import TestClient
    from main import app

    data = _listing_csv([["DEMO-IX", "X0DEMOIMPX", "B0DEMOIMPX", "12,5"], ["DEMO-IY", "X0DEMOIMPY", "B0DEMOIMPY", "abc"]])
    r = TestClient(app).post("/api/master-data/import/listing/apply", files={"file": ("l.csv", data, "text/csv")})
    assert r.status_code == 422
    d = r.json()["detail"]
    assert sorted({e["row"] for e in d["errors"]}) == [2, 3] and "第 2、3 行" in d["message"]


def test_carton_all_bad_422_lists_rows(env):
    from fastapi.testclient import TestClient
    from openpyxl import Workbook
    from main import app
    from fba_tool.product_import import CARTON_TEMPLATE_HEADERS

    wb = Workbook()
    ws = wb.active
    ws.append(CARTON_TEMPLATE_HEADERS)
    ws.append(["DEMO-CB1", "abc", 40, 35, 12, 18])
    ws.append(["DEMO-CB2", 60, -1, 35, 12, 18])
    buf = io.BytesIO()
    wb.save(buf)
    r = TestClient(app).post("/api/master-data/import/carton/apply", files={"file": ("b.xlsx", buf.getvalue(), "application/octet-stream")})
    assert r.status_code == 422, r.text
    d = r.json()["detail"]
    rows = sorted({e["row"] for e in d["errors"]})
    assert len(rows) == 2 and f"第 {rows[0]}、{rows[1]} 行" in d["message"]


def test_edits_all_bad_422_lists_rows(env):
    from fastapi.testclient import TestClient
    from openpyxl import Workbook
    from main import app

    wb = Workbook()
    ws = wb.active
    ws.title = "产品主数据"
    ws.append(["sku", "chinese_name"])
    ws.append(["DEMO-NOT-IN-DB-1", "甲"])
    ws.append(["DEMO-NOT-IN-DB-2", "乙"])
    buf = io.BytesIO()
    wb.save(buf)
    r = TestClient(app).post("/api/master-data/import/edits/apply", files={"file": ("p.xlsx", buf.getvalue())})
    assert r.status_code == 422, r.text
    d = r.json()["detail"]
    assert sorted({e["row"] for e in d["errors"]}) == [2, 3] and "第 2、3 行" in d["message"]
