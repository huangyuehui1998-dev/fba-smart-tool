"""S9-step2-fix M4：Key 无效的各种返回形态都归 LingxingAuthError，定时同步不重试。"""
from __future__ import annotations

import pytest

from fba_tool import lingxing_scheduler as sched
from fba_tool.lingxing_mcp_client import (LingxingAuthError, LingxingMcpError, LingxingUnknownToolError,
                                          unwrap_lingxing_payload)
from test_s9_mcp_protocol import Resp, _client, _text_result
from test_s9fix_mcp_hardening import ErrSearch

KEY_BAD = "MCP Key无效或已失效，请检查x-mcp-key配置"


def _wrap(env):
    return _text_result(env)  # 已是完整 JSON-RPC 响应


@pytest.mark.parametrize("payload", [
    _wrap({"code": 401, "msg": KEY_BAD, "success": False, "data": None}),
    _wrap({"code": "401", "msg": "unauthorized"}),
    _wrap({"code": 403, "msg": "forbidden"}),
    _wrap({"code": 1, "success": True, "data": {"code": 401, "msg": KEY_BAD}}),  # 内层 401
    _wrap({"code": 102, "msg": KEY_BAD, "success": False, "data": None}),
    _wrap({"code": 102, "msg": "MCP Key 无效", "success": False}),
    {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": KEY_BAD}},
    {"jsonrpc": "2.0", "id": 1, "error": {"code": 401, "message": "unauthorized"}},
    {"jsonrpc": "2.0", "id": 1, "error": {"code": 403, "message": "forbidden"}},
])
def test_key_invalid_shapes_are_auth_errors(payload):
    with pytest.raises(LingxingAuthError) as ei:
        unwrap_lingxing_payload(payload)
    assert sched.is_fatal_error(ei.value)


@pytest.mark.parametrize("payload", [
    _wrap({"code": 429, "msg": "请求过于频繁", "success": False}),
    _wrap({"code": 500, "msg": "服务器错误"}),
    _wrap({"code": 102, "msg": "未找到已发布工具: x", "success": False}),
    {"jsonrpc": "2.0", "id": 1, "error": {"code": -32603, "message": "internal error"}},
])
def test_non_auth_errors_not_auth(payload):
    with pytest.raises(LingxingMcpError) as ei:
        unwrap_lingxing_payload(payload)
    assert not isinstance(ei.value, LingxingAuthError)


def test_search_102_with_key_invalid_text_is_auth_not_unknown_tool():
    fake = ErrSearch(Resp(_text_result({"code": 102, "msg": KEY_BAD, "success": False, "data": None})))
    with pytest.raises(LingxingAuthError):
        _client(fake).action("erp_listing", {})
    fake = ErrSearch(Resp(_text_result({"code": 102, "msg": "未找到已发布工具: erp_listing", "success": False})))
    with pytest.raises(LingxingUnknownToolError):
        _client(fake).action("erp_listing", {})


def test_search_envelope_401_is_auth():
    fake = ErrSearch(Resp(_text_result({"code": 401, "msg": KEY_BAD, "success": False})))
    with pytest.raises(LingxingAuthError) as ei:
        _client(fake).action("erp_listing", {})
    assert ei.value.code == 401


class _EnvelopeAuthMcp:
    """listing 返回信封 code=401（经真实 unwrap）——定时同步只试 1 次。"""
    calls = 0

    def __init__(self, payload):
        self.payload = payload

    def initialize(self):
        return {}

    def action(self, tool_id, params=None):
        _EnvelopeAuthMcp.calls += 1
        return unwrap_lingxing_payload(self.payload)

    def iter_pages(self, tool_id, params=None, **kw):
        _EnvelopeAuthMcp.calls += 1
        unwrap_lingxing_payload(self.payload)
        return iter(())

    def paginate(self, tool_id, params=None, **kw):
        _EnvelopeAuthMcp.calls += 1
        unwrap_lingxing_payload(self.payload)
        return []


@pytest.mark.parametrize("payload", [
    _wrap({"code": 401, "msg": KEY_BAD, "success": False}),
    {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": KEY_BAD}},
    _wrap({"code": 102, "msg": KEY_BAD, "success": False}),
])
def test_scheduler_does_not_retry_key_invalid(env, payload):  # noqa: F811
    from test_s5_lingxing_schedule import FAKE_KEY
    from fba_tool import lingxing_sync as ls

    ls.save_lingxing_settings(mcp_key=FAKE_KEY)
    sched.save_schedule({"max_retries": 3, "retry_delay_seconds": 1})
    waits = []
    res = sched.run_once(client_factory=lambda: _EnvelopeAuthMcp(payload), sleep=lambda s: waits.append(s))
    assert not res["ok"]
    assert res["attempts"] == 1 and waits == []


from test_s5_lingxing_schedule import env  # noqa: E402,F401  (fixture)
