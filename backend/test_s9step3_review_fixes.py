"""S9-step3：s9-step2-fix2 复测（99.1）轻微项。全部 mock 领星，临时 app_data。
1 Excel 导入确认写入只跳过坏行；2 价格舍入 ROUND_HALF_UP；3 同一个坏值只提示一次；
4 鉴权判定三条通道同一个函数；5 UI 文案（后端字段）；6 PRICE_MAX 可配置。"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
from pathlib import Path

import pytest

from test_s5_lingxing_schedule import _factory, env  # noqa: F401  (env 是 fixture)
from test_s8fix1_dec12_e2e import _row, _sync
from test_s9_mcp_protocol import _text_result
from fba_tool import lingxing_scheduler as sched
from fba_tool import lingxing_sync as ls
from fba_tool.lingxing_adapter import PRICE_MAX, map_listing_row, parse_price, parse_price_reason, price_max
from fba_tool.lingxing_mcp_client import (
    LingxingAuthError,
    LingxingMcpClient,
    LingxingMcpError,
    is_auth_failure,
    unwrap_lingxing_payload,
)
from fba_tool.lingxing_preview import preview_price_info, promo_drop_text, regular_gap_text, serialize_preview
from fba_tool.master_db import get_product_by_sku
from fba_tool.product_fields import _valid_price

KEY_BAD = "MCP Key无效或已失效，请检查x-mcp-key配置"


def _csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["MSKU", "FNSKU", "ASIN", "价格"])
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8-sig")


# ---------------- 1. Excel 导入：确认写入只跳过坏行 ----------------
def test_import_apply_writes_good_rows_and_lists_skipped(env):
    from fastapi.testclient import TestClient
    from main import app

    data = _csv([["IMP-A", "X0DEMOIMPA", "B0DEMOIMPA", "12.5"],
                 ["IMP-B", "X0DEMOIMPB", "B0DEMOIMPB", "12,5"],
                 ["", "X0DEMOIMPC", "B0DEMOIMPC", "9"],
                 ["IMP-D", "X0DEMOIMPD", "B0DEMOIMPD", "1e30"]])
    r = TestClient(app).post("/api/master-data/import/listing/apply", files={"file": ("l.csv", data, "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["written"] == 1 and body["skipped_rows"] == [3, 4, 5]
    raws = {e["row"]: e["value"] for e in body["skipped"]}
    assert raws[3] == "12,5" and raws[5] == "1e30"
    assert get_product_by_sku("IMP-A")["listing_price"] == pytest.approx(12.5)
    assert get_product_by_sku("IMP-B") is None and get_product_by_sku("IMP-D") is None


def test_import_apply_all_bad_rows_is_422(env):
    from fastapi.testclient import TestClient
    from main import app

    data = _csv([["IMP-X", "X0DEMOIMPX", "B0DEMOIMPX", "12,5"], ["IMP-Y", "X0DEMOIMPY", "B0DEMOIMPY", "0.004"]])
    r = TestClient(app).post("/api/master-data/import/listing/apply", files={"file": ("l.csv", data, "text/csv")})
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert "整个文件未写入" in detail["message"]
    assert [(e["row"], e["value"]) for e in detail["errors"]] == [(2, "12,5"), (3, "0.004")]
    assert get_product_by_sku("IMP-X") is None and get_product_by_sku("IMP-Y") is None


# ---------------- 2. 舍入与报关、发票一致 ----------------
@pytest.mark.parametrize("raw,expect", [
    ("12.005", 12.01), ("0.005", 0.01), ("12.345", 12.35), ("12.344", 12.34), (12.005, 12.01), ("$1,299.995", 1300.0),
])
def test_price_rounding_half_up(raw, expect):
    assert parse_price(raw) == expect


def test_rounding_matches_customs_and_invoice():
    from fba_tool.customs_package import money_half_up
    from fba_tool.invoice_rules import round2

    for raw in ("12.005", "0.005", "2.675", "1.115", "99.995"):
        assert parse_price(raw) == float(money_half_up(raw)) == round2(raw)


def test_still_zero_after_rounding_is_invalid():
    assert parse_price_reason("0.004")[0] is None and "为 0" in parse_price_reason("0.004")[1]


def test_numeric_cells_not_called_scientific():
    assert "科学计数法" not in parse_price_reason(1e-05)[1]
    assert "上限" in parse_price_reason(1e16)[1]
    assert "科学计数法" in parse_price_reason("1e-5")[1]  # 文字写的科学计数法仍然这样提示


# ---------------- 3. 同一个坏值只提示一次 ----------------
def test_duplicate_bad_price_reported_once_in_mapping():
    out = map_listing_row({"msku": "A", "listing_price": "12,5", "price": "12,5", "landed_price": "12,5"})
    assert len(out["price_issues"]) == 1


def test_duplicate_bad_price_once_in_preview_and_diff(env):
    _sync([_row("P-DUP", 15.0, None)])
    bad = _row("P-DUP", "12,5", None)
    bad["landed_price"] = "12,5"
    list(ls.iter_full_sync_events(client=_factory([bad])()))
    con = sqlite3.connect(env / "fba_master.db")
    run_id = con.execute("SELECT MAX(id) FROM lingxing_sync_run").fetchone()[0]
    diffs = con.execute("SELECT message FROM lingxing_sync_diff WHERE run_id=? AND kind='price_invalid'", (run_id,)).fetchall()
    con.close()
    assert len(diffs) == 1 and "12,5" in diffs[0][0]
    pv = serialize_preview(run_id)
    it = [r for g in pv["groups"].values() for r in g if r["sku"] == "P-DUP"][0]
    msgs = [w for w in it["price_info"]["warnings"] if "12,5" in w]
    assert len(msgs) == 1


# ---------------- 4. 鉴权判定：三条通道同一个函数 ----------------
AUTH_CASES = [
    (403, KEY_BAD + "（请求过于频繁）", True),     # 鉴权前缀优先于限流词
    (None, KEY_BAD, True),
    (500, "账号因频繁违规已被禁用", True),        # 禁用 / 封禁 → 不重试
    (403, "账号已封禁", True),
    (429, "account disabled", True),
    (None, "seller banned", True),
    (403, "请求过于频繁，请稍后再试", False),
    (403, "访问太频繁", False),
    (403, "Too Many Requests", False),
    (500, "频繁", False),                        # 宽泛的“频繁”不再算限流词，但也不是鉴权失败
    (403, "频繁", True),                          # 403 不带具体限流短语 → 鉴权失败
    (401, "rate limit", True),
    (429, "请求过于频繁", False),
    (102, "Key无效", True),
    (None, "Key无效", False),
]


@pytest.mark.parametrize("code,msg,fatal", AUTH_CASES)
def test_is_auth_failure_rules(code, msg, fatal):
    assert is_auth_failure(code, msg) is fatal


@pytest.mark.parametrize("code,msg,fatal", [c for c in AUTH_CASES if c[0] not in (None, 102)])
def test_three_channels_agree(code, msg, fatal):
    # 信封
    with pytest.raises(LingxingMcpError) as e1:
        unwrap_lingxing_payload(_text_result({"code": code, "msg": msg, "success": False}))
    # JSON-RPC error
    with pytest.raises(LingxingMcpError) as e2:
        unwrap_lingxing_payload({"jsonrpc": "2.0", "id": 1, "error": {"code": code, "message": msg}})

    # HTTP
    class R:
        def __init__(self):
            self.status_code, self.reason, self.headers, self.text = code, "X", {}, msg

    class S:
        def post(self, *a, **k):
            return R()

    c = LingxingMcpClient("fake-key-for-test", session=S(), min_interval=1.0, sleeper=lambda s: None)
    with pytest.raises(LingxingMcpError) as e3:
        c.initialize()
    got = [isinstance(e.value, LingxingAuthError) for e in (e1, e2, e3)]
    assert got == [fatal, fatal, fatal], (code, msg, got)
    assert all(sched.is_fatal_error(e.value) is fatal for e in (e1, e2, e3))


def test_iserror_uses_same_rule():
    for msg, fatal in ((KEY_BAD, True), ("账号已被禁用", True), ("请求过于频繁", False)):
        payload = {"jsonrpc": "2.0", "id": 1,
                   "result": {"content": [{"type": "text", "text": msg}], "isError": True}}
        with pytest.raises(LingxingMcpError) as ei:
            unwrap_lingxing_payload(payload)
        assert isinstance(ei.value, LingxingAuthError) is fatal


def test_banned_text_not_retried_by_scheduler(env):
    from test_s5_lingxing_schedule import FAKE_KEY
    from test_s9step2fix2_m4_ratelimit import _Envelope403Mcp

    class Banned(_Envelope403Mcp):
        def _fail(self):
            unwrap_lingxing_payload(_text_result({"code": 500, "msg": "账号因频繁违规已被禁用", "success": False}))

    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    sched.save_schedule({"max_retries": 2, "retry_delay_seconds": 1})
    waits = []
    res = sched.run_once(client_factory=lambda: Banned(), sleep=lambda s: waits.append(s))
    assert not res["ok"] and res["attempts"] == 1 and waits == []


# ---------------- 5. UI 文案（后端字段） ----------------
@pytest.mark.parametrize("lp,normal,text", [
    (18.99, 19.99, "低约 5.0%（已超过 5% 阈值）"),
    (18.98, 20.0, "低 5.1%"),
    (18.92, 20.0, "低 5.4%"),
    (15.99, 19.99, "低 20.0%"),
])
def test_promo_text_one_decimal_with_space(lp, normal, text):
    assert promo_drop_text(lp, normal) == text


def test_regular_slightly_above_listing_explained():
    info = preview_price_info({"listing_price": 12.0, "regular_price": 12.5}, None)
    assert info["promo"] is False and info["declared_price"] == 12.0 and info["declared_source_label"] == "售价"
    assert info["regular_gap_text"] == "售价只比领星常规价低 4.0%，未超过 5% 促销阈值，不算促销"
    assert regular_gap_text(12.0, 12.0) == "" and regular_gap_text(10.0, 20.0) == ""
    promo = preview_price_info({"listing_price": 15.99, "regular_price": 19.99}, None)
    assert promo["regular_gap_text"] == "" and promo["declared_source_label"] == "正常价 · 领星常规价"


def test_no_internal_rule_code_or_nested_parens_in_labels():
    from fba_tool.lingxing_preview import PRICE_SOURCE_LABELS

    for label in PRICE_SOURCE_LABELS.values():
        assert "D-12" not in label and "（" not in label
    panel = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "components" / "lingxing-preview-panel.tsx")
    if panel.exists():
        src = panel.read_text(encoding="utf-8")
        assert "（D-12）" not in src and "促销期按正常价申报" in src and "（来源：" not in src


# ---------------- 6. PRICE_MAX 可配置 ----------------
def test_price_max_default_in_config():
    from fba_tool.user_config import DEFAULT_SETTINGS

    cfg = json.loads((Path(__file__).resolve().parent / "config" / "user_settings.default.json").read_text(encoding="utf-8"))
    assert cfg["parameters"]["price_max"] == 100000 == DEFAULT_SETTINGS["parameters"]["price_max"] == PRICE_MAX
    assert price_max() == 100000


def test_price_max_from_settings(monkeypatch):
    import fba_tool.user_config as uc

    monkeypatch.setattr(uc, "param", lambda k, d=None: 500 if k == "price_max" else d)
    assert price_max() == 500
    assert parse_price("600") is None and "上限 500" in parse_price_reason("600")[1]
    assert parse_price("499.99") == 499.99
    assert _valid_price(600.0) is None and _valid_price(400.0) == 400.0


@pytest.mark.parametrize("bad", ["abc", -1, 0, float("nan"), None])
def test_bad_price_max_setting_falls_back(monkeypatch, bad):
    import fba_tool.user_config as uc

    monkeypatch.setattr(uc, "param", lambda k, d=None: bad if k == "price_max" else d)
    assert price_max() == PRICE_MAX
