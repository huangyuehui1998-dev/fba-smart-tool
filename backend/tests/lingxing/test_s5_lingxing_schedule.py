"""S5：领星 MCP 定时自动同步（mock MCP，不连真实领星，不碰真实 app_data）。"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import threading

import pytest

from fba_tool import lingxing_scheduler as sched
from fba_tool import lingxing_sync as ls
from fba_tool import secret_store
from fba_tool.master_db import get_product_by_sku, init_master_db, list_lingxing_sync_diffs, upsert_product
from fba_tool.product_fields import SOURCE_MANUAL, mark_field_sources

FAKE_KEY = "fake-mcp-key-0123456789abcdef"


def _fake_backend():
    return (lambda b: b"ENC:" + b[::-1], lambda b: b[4:][::-1])


@pytest.fixture()
def env(monkeypatch, tmp_path):
    ad = tmp_path / "app_data"
    (ad / "config").mkdir(parents=True)
    (ad / "logs").mkdir()
    monkeypatch.setenv("FBA_APP_DATA_DIR", str(ad))
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    cfgp = ad / "config" / "lingxing.json"
    monkeypatch.setattr(ls, "resolve_config_read", lambda name: cfgp)
    monkeypatch.setattr(ls, "resolve_config_write", lambda name: cfgp)
    old = secret_store._backend
    secret_store.set_backend(_fake_backend())
    init_master_db()
    sched.reset_state()
    yield ad
    secret_store.set_backend(old)
    sched.reset_state()


def _listing(sku, asin, fnsku, price, name="Dog Toy", brand="DemoBrand"):
    return {"msku": sku, "seller_sku": sku, "asin": asin, "fnsku": fnsku, "item_name": name, "brand": brand,
            "sid": 9001, "status": 1, "price": price, "listing_price": price, "currency_code": "USD"}


class MockMcp:
    """只读 mock：记录调用，可设前 n 次失败。"""

    def __init__(self, rows, fail_times=0, hang: threading.Event = None):
        self.rows, self.fail_times, self.hang = rows, fail_times, hang
        self.calls = []

    def initialize(self):
        if self.hang is not None:
            self.hang.wait(5)
        if MockMcp.failures_left > 0:
            MockMcp.failures_left -= 1
            raise ConnectionError("mock：领星 MCP 超时")
        return {}

    def action(self, tool_id, params=None):
        self.calls.append(tool_id)
        return {"data": []}

    def iter_pages(self, tool_id, params=None, **kw):
        self.calls.append(tool_id)
        rows = self.rows if tool_id == "erp_listing" else []
        yield 0, rows, len(rows)

    failures_left = 0


def _factory(rows, fail_times=0, hang=None):
    MockMcp.failures_left = fail_times
    made = []

    def f():
        m = MockMcp(rows, hang=hang)
        made.append(m)
        return m
    f.made = made
    return f


def _config(ad):
    return json.loads((ad / "config" / "lingxing.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 配置：默认关闭、频率可配、校验
def test_default_off_and_interval_configurable(env):
    cfg = sched.load_schedule()
    assert cfg["enabled"] is False
    cfg = sched.save_schedule({"enabled": True, "interval_minutes": 60, "max_retries": 2})
    assert (cfg["enabled"], cfg["interval_minutes"], cfg["max_retries"]) == (True, 60, 2)
    assert _config(env)["auto_sync"]["interval_minutes"] == 60
    for bad in ({"interval_minutes": 5}, {"interval_minutes": "x"}, {"max_retries": 99}):
        with pytest.raises(ValueError):
            sched.save_schedule(bad)


def test_no_apscheduler_dependency():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    assert "apscheduler" not in (root / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "apscheduler" not in (root / "fba_tool" / "lingxing_scheduler.py").read_text(encoding="utf-8").lower().replace("不引入 apscheduler", "")


# ---------------------------------------------------------------- 同步成功：D-02 写入、手填锁定、申报价 D-01 例外
def test_scheduled_sync_writes_from_mcp_keeps_manual_locked_except_price(env):
    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    upsert_product({"sku": "MSKU-1", "asin": "B0OLD", "fnsku": "X-MANUAL", "english_name": "Keep Me",
                    "brand": "LocalBrand", "hs_code": "6307909000"})
    mark_field_sources("MSKU-1", ["fnsku"], SOURCE_MANUAL)
    from fba_tool.product_fields import set_product_fields
    set_product_fields("MSKU-1", {"listing_price": 9.99, "declared_value": 8.88}, SOURCE_MANUAL)

    f = _factory([_listing("MSKU-1", "B0NEWASIN01", "X-REMOTE", 19.99), _listing("MSKU-2", "B0NEWASIN02", "X002", 25.5)])
    res = sched.run_once(client_factory=f)
    assert res["ok"] and res["attempts"] == 1

    p1 = get_product_by_sku("MSKU-1")
    assert p1["asin"] == "B0NEWASIN01"            # MCP 为唯一来源（D-02）
    assert p1["fnsku"] == "X-MANUAL"              # 手填锁定
    assert p1["english_name"] == "Keep Me" and p1["brand"] == "LocalBrand"  # 报关敏感字段本地有值：不自动改
    assert p1["hs_code"] == "6307909000"          # 领星不管的字段不动
    from fba_tool.product_fields import resolve_declared_price
    assert p1["listing_price"] == pytest.approx(9.99)  # 手填售价和领星不同，定时同步默认不覆盖
    assert resolve_declared_price(p1)[0] == pytest.approx(9.99)
    assert p1["declared_value"] == pytest.approx(8.88)  # 手填申报价保留
    p2 = get_product_by_sku("MSKU-2")
    assert p2 and p2["asin"] == "B0NEWASIN02"

    diffs = list_lingxing_sync_diffs(res["run_id"])
    kinds = {d["kind"] for d in diffs}
    assert {"applied", "locked", "needs_review"} <= kinds
    assert any(d["kind"] == "locked" and d["sku"] == "MSKU-1" and d["message"].startswith("fnsku") for d in diffs)
    assert any(
        d["kind"] == "needs_review" and d["sku"] == "MSKU-1" and "9.99" in d["message"] and "19.99" in d["message"]
        for d in diffs
    )
    assert any(d["kind"] == "applied" and "B0OLD" in d["message"] and "B0NEWASIN01" in d["message"] for d in diffs)

    run = sqlite3.connect(env / "fba_master.db").execute(
        "SELECT status, trigger, attempt FROM lingxing_sync_run WHERE id=?", (res["run_id"],)).fetchone()
    assert run == ("auto_applied", "scheduled", 1)


def test_second_run_no_changes(env):
    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    rows = [_listing("MSKU-9", "B0NINE00001", "X009", 12.0)]
    sched.run_once(client_factory=_factory(rows))
    res = sched.run_once(client_factory=_factory(rows))
    assert res["applied"]["written"] == 0


def test_only_read_only_tools_called(env):
    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    f = _factory([_listing("MSKU-1", "B0A", "X1", 1.0)])
    sched.run_once(client_factory=f)
    assert set(f.made[0].calls) <= sched.READ_ONLY_TOOLS
    with pytest.raises(sched.ReadOnlyViolation):
        sched.ReadOnlyClient(f.made[0]).action("update_listing_price", {})


# ---------------------------------------------------------------- 失败：重试 + 日志 + 记录
def test_failure_retries_then_succeeds_and_logs(env):
    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    sched.save_schedule({"max_retries": 3, "retry_delay_seconds": 7})
    waits = []
    res = sched.run_once(client_factory=_factory([_listing("MSKU-1", "B0A", "X1", 1.0)], fail_times=2), sleep=waits.append)
    assert res["ok"] and res["attempts"] == 3 and len(res["run_ids"]) == 3
    assert waits == [7, 14]
    con = sqlite3.connect(env / "fba_master.db")
    rows = con.execute(f"SELECT status, attempt FROM lingxing_sync_run WHERE id IN ({','.join(map(str, res['run_ids']))}) ORDER BY id").fetchall()
    assert rows == [("failed", 1), ("failed", 2), ("auto_applied", 3)]
    assert any(d["kind"] == "retry" for d in list_lingxing_sync_diffs(res["run_ids"][0]))
    log = "\n".join(sched.read_log_tail())
    assert "第 1/4 次失败" in log and "第 3 次成功" in log
    assert FAKE_KEY not in log and "fake****cdef" in log   # 日志只有掩码


def test_all_retries_fail_then_manual_retry(env):
    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    sched.save_schedule({"max_retries": 1, "retry_delay_seconds": 0})
    res = sched.run_once(client_factory=_factory([], fail_times=5), sleep=lambda s: None)
    assert not res["ok"] and res["status"] == "failed" and "重试 2 次仍失败" in res["message"]
    assert sched.status()["last_result"]["status"] == "failed"
    res2 = sched.run_once(client_factory=_factory([_listing("MSKU-1", "B0A", "X1", 1.0)]), trigger=sched.TRIGGER_MANUAL_RETRY)
    assert res2["ok"]
    t = sqlite3.connect(env / "fba_master.db").execute("SELECT trigger FROM lingxing_sync_run WHERE id=?", (res2["run_id"],)).fetchone()
    assert t == ("retry",)


def test_missing_key_fails_without_retry(env):
    res = sched.run_once(client_factory=_factory([]), sleep=lambda s: pytest.fail("不应重试"))
    assert res["status"] == "failed" and "MCP Key" in res["message"]


# ---------------------------------------------------------------- 防重入
def test_lock_prevents_reentry(env):
    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    gate = threading.Event()
    th = threading.Thread(target=sched.run_once, kwargs={"client_factory": _factory([], hang=gate)})
    th.start()
    for _ in range(100):
        if sched.SYNC_LOCK.locked():
            break
        threading.Event().wait(0.02)
    res = sched.run_once(client_factory=_factory([]))
    gate.set()
    th.join(5)
    assert res["status"] == "skipped"
    st = sqlite3.connect(env / "fba_master.db").execute("SELECT status FROM lingxing_sync_run WHERE id=?", (res["run_ids"][0],)).fetchone()
    assert st == ("skipped",)


def _wait_locked():
    for _ in range(250):
        if sched.SYNC_LOCK.locked():
            return True
        threading.Event().wait(0.02)
    return False


def test_manual_stream_and_scheduler_share_lock_concurrently(env, monkeypatch):
    """真实并发：手动一键拉取（API 流式）进行中 → 定时同步跳过；定时同步进行中 → 手动拉取 409。"""
    monkeypatch.setenv("FBA_DISABLE_SCHEDULER", "1")
    from fastapi.testclient import TestClient
    from main import app
    from security import HEADER_NAME, access_token

    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    h = {HEADER_NAME: access_token()} if access_token() else {}
    tc = TestClient(app)

    # A. 手动拉取占着锁（mock 卡在 initialize）
    gate = threading.Event()
    MockMcp.failures_left = 0
    monkeypatch.setattr("fba_tool.lingxing_sync.LingxingMcpClient", lambda *a, **k: MockMcp([], hang=gate))
    out = {}
    th = threading.Thread(target=lambda: out.setdefault("r", tc.post("/api/lingxing/sync/stream", headers=h)))
    th.start()
    assert _wait_locked()
    res = sched.run_once(client_factory=_factory([]))
    assert res["status"] == "skipped"
    gate.set()
    th.join(10)
    assert out["r"].status_code == 200 and not sched.SYNC_LOCK.locked()

    # B. 定时同步占着锁 → 手动拉取、立即重试都 409
    gate2 = threading.Event()
    th2 = threading.Thread(target=sched.run_once, kwargs={"client_factory": _factory([], hang=gate2)})
    th2.start()
    assert _wait_locked()
    assert tc.post("/api/lingxing/sync/stream", headers=h).status_code == 409
    assert tc.post("/api/lingxing/schedule/run-now", headers=h).status_code == 409
    gate2.set()
    th2.join(10)
    assert not sched.SYNC_LOCK.locked()


# ---------------------------------------------------------------- S5-fix1：间隔改动立即重算、启动按上次成功时间补跑
def test_interval_change_recomputes_next_run(env):
    from datetime import datetime, timedelta, timezone
    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    sched.run_once(client_factory=_factory([_listing("MSKU-1", "B0A", "X1", 1.0)]))
    last = sched.last_success_at()
    sched.save_schedule({"enabled": True, "interval_minutes": 600})
    assert datetime.fromisoformat(sched.status()["next_run_at"]) == last + timedelta(minutes=600)
    sched.save_schedule({"interval_minutes": 30})
    assert datetime.fromisoformat(sched.status()["next_run_at"]) == last + timedelta(minutes=30)
    sched.save_schedule({"enabled": False})
    assert sched.status()["next_run_at"] is None


def test_api_interval_change_updates_status(env, monkeypatch):
    monkeypatch.setenv("FBA_DISABLE_SCHEDULER", "1")
    from datetime import datetime, timedelta
    from fastapi.testclient import TestClient
    from main import app
    from security import HEADER_NAME, access_token

    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    sched.run_once(client_factory=_factory([_listing("MSKU-1", "B0A", "X1", 1.0)]))
    h = {HEADER_NAME: access_token()} if access_token() else {}
    tc = TestClient(app)
    a = tc.put("/api/lingxing/schedule", json={"enabled": True, "interval_minutes": 600}, headers=h).json()["status"]["next_run_at"]
    b = tc.put("/api/lingxing/schedule", json={"interval_minutes": 60}, headers=h).json()["status"]
    assert datetime.fromisoformat(a) - datetime.fromisoformat(b["next_run_at"]) == timedelta(minutes=540)
    assert tc.get("/api/lingxing/schedule", headers=h).json()["status"]["next_run_at"] == b["next_run_at"]
    assert b["last_success_at"]


def test_startup_uses_persisted_last_success(env):
    from datetime import datetime, timedelta, timezone
    import sqlite3 as sq
    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    sched.save_schedule({"enabled": True, "interval_minutes": 120})
    now = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    # 从没成功过 → 启动后短延迟补跑
    assert datetime.fromisoformat(sched.compute_next_run(now=now)) == now + timedelta(seconds=sched.CATCH_UP_DELAY_SECONDS)
    con = sq.connect(env / "fba_master.db")
    con.execute("INSERT INTO lingxing_sync_run (started_at, finished_at, status) VALUES (?,?,?)",
                ("x", (now - timedelta(minutes=30)).isoformat(), "auto_applied"))
    con.execute("INSERT INTO lingxing_sync_run (started_at, finished_at, status) VALUES (?,?,?)",
                ("x", (now - timedelta(minutes=5)).isoformat(), "failed"))  # 失败的不算
    con.commit()
    # 上次成功 30 分钟前、间隔 120 → 90 分钟后（模拟“重启”：内存状态清空）
    sched.reset_state()
    assert datetime.fromisoformat(sched.compute_next_run(now=now)) == now + timedelta(minutes=90)
    # 已经过期（上次成功 3 小时前）→ 短延迟补跑
    con.execute("UPDATE lingxing_sync_run SET finished_at=? WHERE status='auto_applied'", ((now - timedelta(hours=3)).isoformat(),))
    con.commit()
    assert datetime.fromisoformat(sched.compute_next_run(now=now)) == now + timedelta(seconds=sched.CATCH_UP_DELAY_SECONDS)


def test_startup_overdue_catches_up_in_loop(env, monkeypatch):
    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    sched.save_schedule({"enabled": True, "interval_minutes": 15})
    monkeypatch.setattr(sched, "CATCH_UP_DELAY_SECONDS", 0.05)
    f = _factory([_listing("MSKU-1", "B0A", "X1", 1.0)])

    async def go():
        sched.reset_state()  # 模拟重启
        sched.start(tick_seconds=0.01, client_factory=f)
        for _ in range(500):
            await asyncio.sleep(0.01)
            if sched.status()["last_result"] and len(f.made) == 1 and sched._state["next_run_at"] and \
                    sched.last_success_at() and sched._state["next_run_at"] != sched._iso(sched.last_success_at()):
                lr = sched.last_success_at()
                from datetime import timedelta as _td
                if sched._state["next_run_at"] == sched._iso(lr + _td(minutes=15)):
                    break
        await sched.stop()

    asyncio.run(go())
    assert sched.status()["last_result"]["ok"] and len(f.made) == 1
    from datetime import datetime, timedelta
    assert datetime.fromisoformat(sched.status()["next_run_at"]) == sched.last_success_at() + timedelta(minutes=15)


# ---------------------------------------------------------------- S5-fix1：不可恢复错误不重试，立即释放锁
class AuthFailMcp(MockMcp):
    def initialize(self):
        from fba_tool.lingxing_mcp_client import LingxingAuthError  # S9-step2 M3：按异常类型判不可恢复
        raise LingxingAuthError("领星 MCP HTTP 401：invalid key", code=401)


@pytest.mark.parametrize("case", ["auth", "whitelist", "nokey"])
def test_fatal_errors_not_retried_and_lock_released(env, monkeypatch, case):
    sched.save_schedule({"max_retries": 3, "retry_delay_seconds": 5})
    if case != "nokey":
        ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    made = []
    if case == "auth":
        factory = lambda: made.append(1) or AuthFailMcp([])
    else:
        MockMcp.failures_left = 0
        factory = lambda: made.append(1) or MockMcp([_listing("MSKU-1", "B0A", "X1", 1.0)])
        if case == "whitelist":
            monkeypatch.setattr(sched, "READ_ONLY_TOOLS", frozenset({"get_my_sids", "get_multi_platform_shop_list"}))
    res = sched.run_once(client_factory=factory, sleep=lambda s: pytest.fail("不可恢复错误不应等待重试"))
    assert not res["ok"] and res["status"] == "failed"
    assert len(made) <= 1 and len(res["run_ids"]) == 1
    assert not sched.SYNC_LOCK.locked()
    if case != "nokey":
        assert res["fatal"] and any(d["kind"] == "fatal" for d in list_lingxing_sync_diffs(res["run_ids"][0]))
    assert sched.run_once(client_factory=_factory([]), sleep=lambda s: None)["status"] != "skipped"


REAL_BAD_KEY_TEXT = "MCP Key无效或已失效，请检查x-mcp-key配置；如无法确认，请在MCP服务管理页重新生成Key后更新客户端配置"  # 真实 MCP 实测原文


class RealBadKeyMcp(MockMcp):
    """按真实领星行为模拟：initialize 成功，tools/call 报 Key 无效。"""

    @staticmethod
    def _bad_key():
        # 走客户端真实的解包：tools/call 返回 isError + Key 无效原文 → LingxingAuthError
        from fba_tool.lingxing_mcp_client import unwrap_lingxing_payload
        unwrap_lingxing_payload({"jsonrpc": "2.0", "id": 2, "result": {
            "content": [{"type": "text", "text": REAL_BAD_KEY_TEXT}], "isError": True}})

    def action(self, tool_id, params=None):
        self._bad_key()

    def iter_pages(self, tool_id, params=None, **kw):
        self._bad_key()
        yield  # pragma: no cover


def test_real_bad_key_text_is_fatal_no_retry(env):
    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    sched.save_schedule({"max_retries": 3, "retry_delay_seconds": 5})
    made = []
    res = sched.run_once(client_factory=lambda: made.append(1) or RealBadKeyMcp([]),
                         sleep=lambda s: pytest.fail("Key 无效不应重试"))
    assert res["fatal"] and len(made) == 1 and "Key无效" in res["message"]
    assert not sched.SYNC_LOCK.locked()


def test_is_fatal_error_classifier():
    """S9-step2 M3：按异常类型判断，不看文字。"""
    from fba_tool.lingxing_mcp_client import (LingxingAuthError, LingxingMcpError, LingxingReadOnlyError,
                                              LingxingUnknownToolError)
    assert sched.is_fatal_error(LingxingAuthError(REAL_BAD_KEY_TEXT))
    assert sched.is_fatal_error(LingxingAuthError("领星 MCP HTTP 403：forbidden", code=403))
    assert sched.is_fatal_error(LingxingReadOnlyError("x"))
    assert sched.is_fatal_error(LingxingUnknownToolError("x", code=102))
    assert sched.is_fatal_error(sched.ReadOnlyViolation("定时同步只允许只读调用，拒绝 x"))
    assert not sched.is_fatal_error(LingxingMcpError("领星 MCP HTTP 500：Internal Server Error", code=500))
    assert not sched.is_fatal_error(LingxingMcpError("领星 MCP 网络错误：timed out"))
    # 文字里带“未知工具”“Key无效”也不算：只看类型
    assert not sched.is_fatal_error(LingxingMcpError("请求过于频繁（未知工具 / Key无效 字样）", code=429))
    assert not sched.is_fatal_error("领星 MCP 未知工具 x")


# ---------------------------------------------------------------- asyncio 定时循环
def test_asyncio_loop_runs_when_due_and_not_when_disabled(env):
    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    f = _factory([_listing("MSKU-1", "B0A", "X1", 1.0)])

    async def go(enabled):
        sched.reset_state()
        sched.save_schedule({"enabled": enabled, "interval_minutes": 15})
        sched._state["next_run_at"] = "2000-01-01T00:00:00+00:00" if enabled else None
        sched.start(tick_seconds=0.01, client_factory=f)
        for _ in range(300):
            await asyncio.sleep(0.01)
            # 等结果写入且下次时间已更新（run_once 先写 last_result，循环随后才重算下次时间）
            if sched.status()["last_result"] and (sched._state["next_run_at"] or "") > "2026":
                break
        await sched.stop()

    asyncio.run(go(False))
    assert sched.status()["last_result"] is None and not f.made
    asyncio.run(go(True))
    assert sched.status()["last_result"]["ok"]
    assert sched.status()["next_run_at"] > "2026"


# ---------------------------------------------------------------- 密钥：DPAPI
def test_key_stored_as_dpapi_ciphertext_only(env):
    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    sched.save_schedule({"enabled": True})
    raw = (env / "config" / "lingxing.json").read_text(encoding="utf-8")
    assert FAKE_KEY not in raw and "mcp_key_enc" in raw and '"mcp_key"' not in raw


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="真实 DPAPI 只在 Windows 上")
def test_real_dpapi_roundtrip():
    secret_store.set_backend(secret_store._dpapi())
    tok = secret_store.protect(FAKE_KEY)
    assert FAKE_KEY not in tok and secret_store.unprotect(tok) == FAKE_KEY


# ---------------------------------------------------------------- API：界面能看到记录和差异
def test_api_schedule_runs_diffs_log(env, monkeypatch):
    monkeypatch.setenv("FBA_DISABLE_SCHEDULER", "1")
    from fastapi.testclient import TestClient
    from main import app
    from security import HEADER_NAME, access_token

    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    tc = TestClient(app)
    h = {HEADER_NAME: access_token()} if access_token() else {}
    assert tc.get("/api/lingxing/schedule", headers=h).json()["config"]["enabled"] is False
    r = tc.put("/api/lingxing/schedule", json={"enabled": True, "interval_minutes": 30}, headers=h)
    assert r.status_code == 200 and r.json()["config"]["interval_minutes"] == 30
    assert tc.put("/api/lingxing/schedule", json={"interval_minutes": 1}, headers=h).status_code == 422

    monkeypatch.setattr("fba_tool.lingxing_mcp_client.LingxingMcpClient",
                        lambda *a, **k: MockMcp([_listing("MSKU-1", "B0A", "X1", 3.0)]))
    MockMcp.failures_left = 0
    r = tc.post("/api/lingxing/schedule/run-now", headers=h)
    assert r.status_code == 200 and r.json()["ok"], r.text
    items = tc.get("/api/lingxing/runs", headers=h).json()["items"]
    assert items[0]["trigger"] == "retry" and items[0]["diff_counts"].get("applied")
    d = tc.get(f"/api/lingxing/runs/{items[0]['id']}", headers=h).json()
    assert any(x["kind"] == "applied" for x in d["diffs"])
    assert tc.get("/api/lingxing/runs/999999", headers=h).status_code == 404
    assert any("成功" in line for line in tc.get("/api/lingxing/sync-log", headers=h).json()["lines"])


def test_real_app_data_unchanged_by_s5_flows(env):
    import hashlib
    from pathlib import Path

    real = Path(__file__).resolve().parents[2].parent / "app_data"

    def tree(p):
        if not p.exists():
            return {}
        return {str(f.relative_to(p)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(p.rglob("*")) if f.is_file()}

    before = tree(real)
    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    sched.save_schedule({"enabled": True, "max_retries": 1, "retry_delay_seconds": 0})
    sched.run_once(client_factory=_factory([_listing("MSKU-1", "B0A", "X1", 1.0)], fail_times=1), sleep=lambda s: None)
    assert tree(real) == before
