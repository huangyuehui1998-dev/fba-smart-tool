"""S9-step2-fix2 N5 / N6：403 带限流意思可以重试；JSON-RPC 只认 401/403 或以领星鉴权原文开头。"""
from __future__ import annotations

import pytest

from fba_tool import lingxing_scheduler as sched
from fba_tool.lingxing_mcp_client import LingxingAuthError, LingxingMcpError, LingxingMcpClient, unwrap_lingxing_payload
from test_s9_mcp_protocol import _text_result

KEY_BAD = "MCP Key无效或已失效，请检查x-mcp-key配置"


@pytest.mark.parametrize("payload", [
    _text_result({"code": 403, "msg": "请求过于频繁，请稍后再试", "success": False}),
    _text_result({"code": 403, "msg": "rate limit exceeded"}),
    _text_result({"code": "403", "msg": "接口限流"}),
    {"jsonrpc": "2.0", "id": 1, "error": {"code": 403, "message": "Too many requests"}},
    {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "rate limited (MCP Key无效 字样)"}},
    {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "Key 无效？请稍后重试"}},
    {"jsonrpc": "2.0", "id": 1, "error": "MCP Key 无效"},
])
def test_rate_limit_and_text_only_are_retryable(payload):
    with pytest.raises(LingxingMcpError) as ei:
        unwrap_lingxing_payload(payload)
    assert not isinstance(ei.value, LingxingAuthError) and not sched.is_fatal_error(ei.value)


@pytest.mark.parametrize("payload", [
    _text_result({"code": 403, "msg": "forbidden"}),
    _text_result({"code": 401, "msg": "rate limit"}),  # 401 一律鉴权失败
    {"jsonrpc": "2.0", "id": 1, "error": {"code": 403, "message": "forbidden"}},
    {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": KEY_BAD}},
    {"jsonrpc": "2.0", "id": 1, "error": {"message": "  " + KEY_BAD}},
])
def test_auth_still_fatal(payload):
    with pytest.raises(LingxingAuthError):
        unwrap_lingxing_payload(payload)


@pytest.mark.parametrize("status,text,fatal", [
    (403, "rate limit exceeded", False),
    (403, "Too Many Requests", False),
    (403, "请求过于频繁", False),
    (403, "forbidden", True),
    (401, "rate limit", True),
])
def test_http_403_rate_limit_retryable(status, text, fatal):
    class R:
        def __init__(self):
            self.status_code, self.reason, self.headers, self.text = status, "X", {}, text

    class S:
        def post(self, *a, **k):
            return R()

    c = LingxingMcpClient("fake-key-for-test", session=S(), min_interval=1.0, sleeper=lambda s: None)
    with pytest.raises(LingxingMcpError) as ei:
        c.initialize()
    assert sched.is_fatal_error(ei.value) is fatal


class _Envelope403Mcp:
    def initialize(self):
        return {}

    def _fail(self):
        unwrap_lingxing_payload(_text_result({"code": 403, "msg": "请求过于频繁", "success": False}))

    def action(self, tool_id, params=None):
        self._fail()

    def iter_pages(self, tool_id, params=None, **kw):
        self._fail()
        return iter(())

    def paginate(self, tool_id, params=None, **kw):
        self._fail()
        return []


def test_scheduler_retries_403_rate_limit(env):  # noqa: F811
    from test_s5_lingxing_schedule import FAKE_KEY
    from fba_tool import lingxing_sync as ls

    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    sched.save_schedule({"max_retries": 2, "retry_delay_seconds": 1})
    waits = []
    res = sched.run_once(client_factory=lambda: _Envelope403Mcp(), sleep=lambda s: waits.append(s))
    assert not res["ok"] and res["attempts"] == 3 and len(waits) == 2


from test_s5_lingxing_schedule import env  # noqa: E402,F401  (fixture)
