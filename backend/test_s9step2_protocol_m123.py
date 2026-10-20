"""S9-step2 M1–M3：_rpc 只放行已知 method / 工具名（先整理再判断）、success 必须是布尔 True、致命错误按类型判断。"""
from __future__ import annotations

import pytest

from fba_tool import lingxing_scheduler as sched
from fba_tool.lingxing_mcp_client import (LingxingAuthError, LingxingMcpError, LingxingReadOnlyError,
                                          LingxingUnknownToolError, unwrap_lingxing_payload)
from test_s9_mcp_protocol import SCHEMAS, FakeLingxing, Resp, _client, _names, _text_result
from test_s9fix_mcp_hardening import ErrSearch


def _ready(**kw):
    fake = FakeLingxing(**kw)
    c = _client(fake)
    c.initialize()
    return fake, c


# ---------------- M1 ----------------
@pytest.mark.parametrize("method,name", [
    ("tools/call", "Action"), ("tools/call", " action "), ("TOOLS/CALL", "action"), (" Tools/Call ", "ACTION"),
])
def test_variant_spellings_still_guarded_write_rejected(method, name):
    fake, c = _ready(extra_tools={"erp_listing": dict(SCHEMAS["erp_listing"], toolType="write")})
    with pytest.raises(LingxingReadOnlyError):
        c._rpc(method, {"name": name, "arguments": {"toolId": "erp_listing", "params": {}}})
    assert "action" not in _names(fake)


def test_variant_spellings_normalized_when_allowed():
    fake, c = _ready()
    c._rpc(" TOOLS/CALL ", {"name": " Action ", "arguments": {"toolId": "  erp_listing \t", "params": {}}})
    sent = [(m, n, t) for m, n, t, _s, _k in fake.log if m == "tools/call"]
    assert sent == [("tools/call", "search", "erp_listing"), ("tools/call", "action", "erp_listing")]


def test_tool_id_with_whitespace_via_action():
    fake = FakeLingxing()
    _client(fake).action("  erp_listing  ", {})
    assert [t for _m, n, t, _s, _k in fake.log if n in ("search", "action")] == ["erp_listing", "erp_listing"]


@pytest.mark.parametrize("params", [
    [{"name": "action"}],                                  # params 是列表
    "action",                                              # params 是字符串
    {"name": "action", "arguments": ["erp_listing"]},      # arguments 是列表
    {"name": "action", "arguments": {"toolId": "erp_listing", "params": [1, 2]}},  # action params 是列表
])
def test_non_dict_params_rejected(params):
    fake, c = _ready()
    with pytest.raises(LingxingReadOnlyError):
        c._rpc("tools/call", params)
    assert "action" not in _names(fake)


@pytest.mark.parametrize("method,params", [
    ("tools/list", {}), ("resources/read", {"uri": "x"}), ("", None),
    ("tools/call", {"name": "update_listing_price", "arguments": {}}),
    ("tools/call", {"name": "", "arguments": {}}),
])
def test_unknown_method_or_tool_name_rejected(method, params):
    fake, c = _ready()
    n0 = len(fake.log)
    with pytest.raises(LingxingReadOnlyError):
        c._rpc(method, params)
    assert len(fake.log) == n0  # 一个请求都没发


# ---------------- M2 ----------------
@pytest.mark.parametrize("success", ["false", "true", 1, 0, None, "True"])
def test_success_must_be_bool_true(success):
    with pytest.raises(LingxingMcpError):
        unwrap_lingxing_payload(_text_result({"success": success, "data": {"list": []}}))
    with pytest.raises(LingxingMcpError):
        unwrap_lingxing_payload(_text_result({"code": 1, "success": success, "data": {"list": []}}))
    with pytest.raises(LingxingMcpError):  # 内层也一样
        unwrap_lingxing_payload(_text_result({"code": 1, "data": {"code": 1, "success": success, "data": {}}}))


def test_success_true_ok():
    assert unwrap_lingxing_payload(_text_result({"code": 1, "success": True, "data": {"list": []}}))["code"] == 1


# ---------------- M3 ----------------
def test_429_with_unknown_tool_text_is_retryable():
    fake = ErrSearch(Resp(_text_result({"code": 429, "msg": "请求过于频繁：未找到已发布工具 / 未知工具", "success": False})))
    with pytest.raises(LingxingMcpError) as ei:
        _client(fake).action("erp_listing", {})
    assert not isinstance(ei.value, LingxingUnknownToolError)
    assert not sched.is_fatal_error(ei.value)


def test_code_102_raises_typed_unknown_tool():
    fake = ErrSearch(Resp(_text_result({"code": 102, "msg": "未找到已发布工具: erp_listing", "success": False, "data": None})))
    with pytest.raises(LingxingUnknownToolError) as ei:
        _client(fake).action("erp_listing", {})
    assert ei.value.code == 102 and sched.is_fatal_error(ei.value)


def test_readonly_and_auth_are_typed():
    fake, c = _ready()
    with pytest.raises(LingxingReadOnlyError):
        c.action("update_listing_price", {})
    with pytest.raises(LingxingAuthError):
        unwrap_lingxing_payload({"jsonrpc": "2.0", "id": 1, "result": {
            "content": [{"type": "text", "text": "MCP Key无效或已失效，请检查x-mcp-key配置"}], "isError": True}})
    # 限流文字里带“Key无效”但不是以领星鉴权原文开头 → 普通错误，可重试
    with pytest.raises(LingxingMcpError) as ei:
        unwrap_lingxing_payload({"jsonrpc": "2.0", "id": 1, "result": {
            "content": [{"type": "text", "text": "rate limited (MCP Key无效 字样)"}], "isError": True}})
    assert not isinstance(ei.value, LingxingAuthError) and not sched.is_fatal_error(ei.value)


def test_http_401_typed_auth_and_500_retryable():
    class R:
        def __init__(self, status):
            self.status_code, self.reason, self.headers, self.text = status, "X", {}, "err"

    class S:
        def __init__(self, status):
            self.status = status

        def post(self, *a, **k):
            return R(self.status)

    from fba_tool.lingxing_mcp_client import LingxingMcpClient
    for status, fatal in ((401, True), (403, True), (500, False), (429, False)):
        c = LingxingMcpClient("fake-key-for-test", session=S(status), min_interval=1.0, sleeper=lambda s: None)
        with pytest.raises(LingxingMcpError) as ei:
            c.initialize()
        assert sched.is_fatal_error(ei.value) is fatal, status


class _RateLimitedMcp:
    """listing 第一次报“限流”（文字里带“未知工具”），第二次成功：定时同步应当重试而不是停。"""
    calls = 0

    def __init__(self, rows):
        from test_s5_lingxing_schedule import MockMcp
        self._inner = MockMcp(rows)

    def initialize(self):
        return self._inner.initialize()

    def action(self, tool_id, params=None):
        return self._inner.action(tool_id, params)

    def iter_pages(self, tool_id, params=None, **kw):
        _RateLimitedMcp.calls += 1
        if _RateLimitedMcp.calls == 1:
            raise LingxingMcpError("请求过于频繁（429），未知工具 字样只是原文的一部分", code=429)
        return self._inner.iter_pages(tool_id, params, **kw)

    def paginate(self, tool_id, params=None, **kw):
        return self._inner.paginate(tool_id, params, **kw)


def test_scheduler_retries_rate_limit_with_unknown_tool_text(env):  # noqa: F811
    from test_s5_lingxing_schedule import FAKE_KEY, MockMcp, _listing
    from fba_tool import lingxing_sync as ls

    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    sched.save_schedule({"max_retries": 2, "retry_delay_seconds": 1})
    MockMcp.failures_left = 0
    _RateLimitedMcp.calls = 0
    waits = []
    res = sched.run_once(client_factory=lambda: _RateLimitedMcp([_listing("MSKU-1", "B0A", "X1", 1.0)]),
                         sleep=lambda s: waits.append(s))
    assert res["ok"] and res["attempts"] == 2 and waits == [1]


from test_s5_lingxing_schedule import env  # noqa: E402,F401  (fixture)
