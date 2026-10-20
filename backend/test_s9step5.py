"""S9-step5（S9-final 收尾）：N5 导入时 SKU 大小写冲突（预览直接报、确认整体不写、批量写入一个事务回滚）、
N6 确认成功提示用独立 toast id、N7 护栏补测（仓库根 app_data、文件变化后重查、会话结束扫描）和「正好 90 天」。
全部用 tmp_path / 临时 FBA_APP_DATA_DIR 里的示例数据（DEMO-*），不碰真实数据。"""
from __future__ import annotations

import io
import os
import re
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import realdata_guard as rg
from test_s5_lingxing_schedule import env  # noqa: F401  (fixture)
from test_s9step4fix3 import DB, SESS, _fake_real, _listing_csv

BACKEND = Path(__file__).resolve().parent
ROOT = BACKEND.parent


# ======================= N5：导入时 SKU 大小写冲突 =======================

def _two_case(env, base="DEMO-CC"):
    con = sqlite3.connect(env / "fba_master.db")
    for s in (base, base.lower()):
        con.execute("INSERT INTO product_master (sku, updated_at) VALUES (?, '2026-01-01T00:00:00+00:00')", (s,))
    con.commit()
    con.close()


def _skus(env):
    con = sqlite3.connect(env / "fba_master.db")
    try:
        return sorted(r[0] for r in con.execute("SELECT sku FROM product_master"))
    finally:
        con.close()


def _rows(env, sql):
    con = sqlite3.connect(env / "fba_master.db")
    try:
        return [tuple(r) for r in con.execute(sql)]
    finally:
        con.close()


def _carton_xlsx(rows):
    from openpyxl import Workbook
    from fba_tool.product_import import CARTON_TEMPLATE_HEADERS

    wb = Workbook()
    ws = wb.active
    ws.append(CARTON_TEMPLATE_HEADERS)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _client():
    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app)


def test_listing_preview_reports_case_conflict_row(env):
    from fba_tool.product_import import preview_listing_import

    _two_case(env)
    data = _listing_csv([["Demo-Cc", "X0DEMOCC01", "B0DEMOCC01", "12.5"], ["DEMO-OK1", "X0DEMOOK01", "B0DEMOOK01", "13"]])
    out = preview_listing_import(data, "l.csv")
    assert out["conflict_rows"] == [2]
    errs = [e for e in out["errors"] if e["row"] == 2]
    assert errs and errs[0]["field"] == "sku" and "第2行" in errs[0]["message"] and "大小写" in errs[0]["message"]
    assert all(it["sku"] != "Demo-Cc" for it in out.get("items", []))


def test_listing_preview_exact_case_is_not_conflict(env):
    from fba_tool.product_import import preview_listing_import

    _two_case(env)
    out = preview_listing_import(_listing_csv([["DEMO-CC", "X0DEMOCC01", "B0DEMOCC01", "12.5"]]), "l.csv")
    assert out["conflict_rows"] == [] and out["errors"] == []


def test_listing_apply_conflict_writes_nothing(env):
    _two_case(env)
    before = _skus(env)
    data = _listing_csv([["DEMO-OK1", "X0DEMOOK01", "B0DEMOOK01", "13"], ["Demo-Cc", "X0DEMOCC01", "B0DEMOCC01", "12.5"]])
    r = _client().post("/api/master-data/import/listing/apply", files={"file": ("l.csv", data, "text/csv")})
    assert r.status_code == 422, r.text
    d = r.json()["detail"]
    assert [e["row"] for e in d["errors"]] == [3] and "整个文件未写入" in d["message"] and "大小写" in d["message"]
    assert _skus(env) == before  # DEMO-OK1 也没写


def test_carton_preview_and_apply_conflict(env):
    from fba_tool.product_import import preview_carton_import

    _two_case(env, "DEMO-CT")
    data = _carton_xlsx([["DEMO-CB-OK", 60, 40, 35, 12, 18], ["demo-Ct", 60, 40, 35, 12, 18]])
    out = preview_carton_import(data, "b.xlsx")
    assert len(out["conflict_rows"]) == 1
    row = out["conflict_rows"][0]
    assert any(e["row"] == row and "大小写" in e["message"] for e in out["errors"])
    before = _rows(env, "SELECT * FROM product_master ORDER BY sku")
    r = _client().post("/api/master-data/import/carton/apply", files={"file": ("b.xlsx", data, "application/octet-stream")})
    assert r.status_code == 422, r.text
    assert [e["row"] for e in r.json()["detail"]["errors"]] == [row]
    assert _rows(env, "SELECT * FROM product_master ORDER BY sku") == before


def test_apply_rolls_back_whole_batch_on_midway_error(env, monkeypatch):
    from fba_tool import product_import

    real = product_import.set_product_fields
    calls = []

    def boom(sku, vals, source):
        calls.append(sku)
        if len(calls) == 2:
            raise RuntimeError("模拟中途出错")
        return real(sku, vals, source)

    monkeypatch.setattr(product_import, "set_product_fields", boom)
    before = _rows(env, "SELECT * FROM product_master ORDER BY sku")
    data = _listing_csv([["DEMO-RB1", "X0DEMORB01", "B0DEMORB01", "13"], ["DEMO-RB2", "X0DEMORB02", "B0DEMORB02", "14"]])
    with pytest.raises(RuntimeError):
        product_import.apply_listing_import(data, "l.csv")
    assert len(calls) == 2
    assert _rows(env, "SELECT * FROM product_master ORDER BY sku") == before  # 第一条也回滚了
    monkeypatch.setattr(product_import, "set_product_fields", real)
    out = product_import.apply_listing_import(data, "l.csv")  # 之后正常写入不受影响
    assert out["written"] == 2 and {"DEMO-RB1", "DEMO-RB2"} <= set(_skus(env))


def test_batch_transaction_commits_once_and_nests(env):
    from fba_tool import master_db

    with master_db.batch_transaction() as outer:
        master_db.upsert_product({"sku": "DEMO-BT1"})
        with master_db.batch_transaction() as inner:
            assert inner is outer and master_db._connect() is outer
            master_db.upsert_product({"sku": "DEMO-BT2"})
        assert "DEMO-BT1" not in _skus(env)  # 还没提交（另一个连接看不到）
    assert {"DEMO-BT1", "DEMO-BT2"} <= set(_skus(env))
    assert master_db._connect() is not outer


# ======================= N6：确认成功提示用独立 toast id =======================

def test_confirm_success_toast_has_own_id():
    src = (ROOT / "frontend" / "src" / "components" / "lingxing-preview-panel.tsx").read_text(encoding="utf-8")
    m_err = re.search(r"const toastId = `([^`]+)`", src)
    m_ok = re.search(r"const okToastId = `([^`]+)`", src)
    assert m_err and m_ok and m_err.group(1) != m_ok.group(1)
    assert "toast.dismiss(toastId)" in src
    assert re.search(r"toast\.success\([^;]*\{ id: okToastId \}\)", src)
    assert not re.search(r"toast\.success\([^;]*\{ id: toastId \}\)", src)
    assert re.search(r"toast\.error\([^;]*\{ id: toastId \}\)", src)


# ======================= N7：护栏补测 =======================

def test_guard_covers_repo_root_app_data(tmp_path):
    """仓库根目录下的 app_data/（开发时直接运行产生的真实数据）也算真实来源。"""
    backend = tmp_path / "proj" / "backend"
    backend.mkdir(parents=True)
    _fake_real(tmp_path / "proj" / "app_data_src")
    ad_real = tmp_path / "proj" / "app_data"
    (ad_real / "sessions" / "history").mkdir(parents=True)
    shutil.copy2(tmp_path / "proj" / "app_data_src" / DB, ad_real / DB)
    shutil.copy2(tmp_path / "proj" / "app_data_src" / SESS, ad_real / "sessions" / "autosave.json")
    shutil.rmtree(tmp_path / "proj" / "app_data_src")
    srcs = rg.real_sources(backend, tmp_path / "proj")
    assert sorted(p.relative_to(tmp_path / "proj").as_posix() for p in srcs) == ["app_data/fba_master.db", "app_data/sessions/autosave.json"]
    idx = rg.RealDataIndex(srcs)
    tmp_ad = tmp_path / "tmp_ad"
    tmp_ad.mkdir()
    shutil.copyfile(ad_real / DB, tmp_ad / "x.db")
    shutil.copyfile(ad_real / "sessions" / "autosave.json", tmp_ad / "s.json")
    assert sorted(f.split(":")[0] for f in idx.find_copies(tmp_ad)) == ["s.json", "x.db"]
    os.remove(tmp_ad / "x.db")
    os.remove(tmp_ad / "s.json")


def test_guard_rechecks_file_after_change(tmp_path):
    """缓存只对没变的文件生效：内容 / mtime 变了要重新判断。"""
    real = _fake_real(tmp_path / "real")
    idx = rg.RealDataIndex(rg.real_sources(real, tmp_path / "noroot"))
    ad = tmp_path / "ad"
    (ad / "sessions").mkdir(parents=True)
    target = ad / "sessions" / "s.json"
    target.write_bytes(b"x" * (real / SESS).stat().st_size)
    assert idx.find_copies(ad) == []
    shutil.copyfile(real / SESS, target)  # 同大小，内容换成真实副本
    st = target.stat()
    os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))
    assert [f.split(":")[0] for f in idx.find_copies(ad)] == ["sessions/s.json"]
    target.write_bytes(b"y" * (real / SESS).stat().st_size)  # 再改回非副本
    os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns + 4_000_000_000))
    assert idx.find_copies(ad) == []


class _FakeFactory:
    def __init__(self, base):
        self._base = base

    def getbasetemp(self):
        return self._base


class _FakeConfig:
    def __init__(self, base):
        self._tmp_path_factory = _FakeFactory(base)


class _FakeSession:
    def __init__(self, base):
        self.config = _FakeConfig(base)
        self.exitstatus = 0


def test_sessionfinish_scan_fails_session_on_copy(tmp_path, monkeypatch, capsys):
    import conftest

    real = _fake_real(tmp_path / "real")
    monkeypatch.setattr(conftest, "_REAL_INDEX", rg.RealDataIndex(rg.real_sources(real, tmp_path / "noroot")))
    global_ad = tmp_path / "global_ad"
    base = tmp_path / "basetemp"
    global_ad.mkdir()
    (base / "t0").mkdir(parents=True)
    monkeypatch.setattr(conftest, "_TMP_APP_DATA", str(global_ad))

    s = _FakeSession(base)
    conftest.pytest_sessionfinish(s, 0)
    assert s.exitstatus == 0  # 没有副本 → 不改结果

    shutil.copyfile(real / DB, base / "t0" / "leak.db")  # 某个测试的 tmp_path 里留了副本
    s = _FakeSession(base)
    conftest.pytest_sessionfinish(s, 0)
    assert s.exitstatus == 1
    out = capsys.readouterr().out
    assert "真实数据护栏" in out and "leak.db" in out
    os.remove(base / "t0" / "leak.db")

    shutil.copyfile(real / SESS, global_ad / "autosave.json")  # 全局临时 app_data 里的副本也查
    s = _FakeSession(base)
    conftest.pytest_sessionfinish(s, 0)
    assert s.exitstatus == 1
    os.remove(global_ad / "autosave.json")


# ======================= N7：「正好 90 天」用固定的当前时间 =======================

def test_window_exact_90_days_with_fixed_now(monkeypatch):
    from fba_tool import product_fields

    now = datetime(2026, 10, 17, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(product_fields, "_utcnow", lambda: now)
    exact = now - timedelta(days=90)
    assert product_fields._in_window(exact.isoformat()) is True
    assert product_fields._in_window((exact - timedelta(microseconds=1)).isoformat()) is False
    assert product_fields._in_window((exact + timedelta(seconds=1)).isoformat()) is True
    assert product_fields.regular_price_in_window({"regular_price": 20.0, "regular_price_at": exact.isoformat()}) is True
