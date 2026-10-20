"""S9-step1-fix：N12–N15 协议层加固测试（全 mock，不连真实领星）。"""
from __future__ import annotations

import json

import pytest

from fba_tool import lingxing_mcp_client as mc
from fba_tool.lingxing_mcp_client import LingxingMcpClient, LingxingMcpError, extract_list, unwrap_lingxing_payload
from fba_tool.lingxing_scheduler import is_fatal_error
from test_s9_mcp_protocol import SCHEMAS, FakeLingxing, Resp, _client, _names, _text_result


def _raw(text, rid=1):
    return {"jsonrpc": "2.0", "id": rid, "result": {"content": [{"type": "text", "text": text}], "isError": False}}


# ---------------- N14：失败形态一律报错 ----------------
@pytest.mark.parametrize("env", [
    {"code": 0, "msg": "外层失败", "data": {"list": []}},          # 外层 code=0，没有 success 键
    {"code": 102, "msg": "未找到", "data": None},                  # 外层 code=102，没有 success 键
    {"code": 1, "success": True, "data": {"code": 500, "msg": "服务异常"}},             # 内层 500 无 data
    {"code": 1, "success": True, "data": {"code": 0, "msg": "内层失败", "data": {"list": []}}},  # 内层 0 带 data
    {"code": 1, "success": True, "data": "系统繁忙"},              # data 是字符串
    {"success": True, "code": 0, "data": {"list": []}},            # 有 success 但 code=0
], ids=["outer0", "outer102", "inner500", "inner0_with_data", "data_str", "success_true_code0"])
def test_failure_envelopes_raise(env):
    with pytest.raises(LingxingMcpError):
        unwrap_lingxing_payload(_text_result(env))


def test_content_not_json_raises():
    with pytest.raises(LingxingMcpError, match="不是 JSON"):
        unwrap_lingxing_payload(_raw("rate limited, try later"))
    with pytest.raises(LingxingMcpError, match="不是 JSON"):
        unwrap_lingxing_payload("<html>502</html>")


def test_legacy_success_only_formats_still_ok():
    assert extract_list(unwrap_lingxing_payload(_text_result({"success": True, "data": {"list": [{"a": 1}]}}))) == [{"a": 1}]
    with pytest.raises(LingxingMcpError):
        unwrap_lingxing_payload(_text_result({"success": False, "msg": "无权限"}))
    ok = unwrap_lingxing_payload(_text_result({"code": "1", "data": {"code": 1, "data": {"list": [{"b": 2}], "total": 1}}}))
    assert extract_list(ok) == [{"b": 2}]
    # 非信封（initialize 结果、search 的 data 本身没有 code）不受影响
    assert unwrap_lingxing_payload({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "x"}}) == {"protocolVersion": "x"}
    # 可重复解包
    once = unwrap_lingxing_payload(_text_result({"code": 1, "data": {"code": 1, "data": {"list": []}}}))
    assert unwrap_lingxing_payload(once) == once


# ---------------- N12：search 的错误分类 ----------------
class ErrSearch(FakeLingxing):
    def __init__(self, search_resp, **kw):
        super().__init__(**kw)
        self.search_resp = search_resp

    def post(self, url, headers=None, data=None, timeout=None):
        raw = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
        if (raw.get("params") or {}).get("name") == "search":
            self.log.append(("tools/call", "search", raw["params"]["arguments"].get("toolId"), None, None))
            return self.search_resp
        return super().post(url, headers=headers, data=data, timeout=timeout)


class TextResp:
    def __init__(self, text, ctype="application/json", status=200):
        self.status_code = status
        self.reason = "X"
        self.headers = {"Content-Type": ctype}
        self.text = text


@pytest.mark.parametrize("resp,label", [
    (TextResp(json.dumps(_raw("rate limited"))), "rate limited 非 JSON"),
    (Resp(_text_result({"code": 429, "msg": "请求过于频繁，限流"})), "限流 code"),
    (TextResp("event: message\n\n", ctype="text/event-stream"), "空 SSE"),
    (TextResp("<html>bad gateway</html>"), "非 JSON 正文"),
    (TextResp("upstream error", status=503), "HTTP 503"),
])
def test_search_transient_errors_not_unknown_and_block_action(resp, label):
    fake = ErrSearch(resp)
    c = _client(fake)
    with pytest.raises(LingxingMcpError) as ei:
        c.action("erp_listing", {})
    assert "未知工具" not in str(ei.value), label
    assert not is_fatal_error(ei.value), label  # 可重试（按类型）
    assert "action" not in _names(fake)


def test_search_code_102_is_unknown_and_fatal():
    fake = ErrSearch(Resp(_text_result({"code": 102, "data": None, "msg": "未找到已发布工具: erp_listing", "success": False})))
    c = _client(fake)
    with pytest.raises(LingxingMcpError, match="未知工具") as ei:
        c.action("erp_listing", {})
    assert is_fatal_error(ei.value) and "action" not in _names(fake)


def test_search_unknown_text_without_code_is_unknown():
    fake = ErrSearch(Resp({"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "x"}], "isError": True}}))
    fake.search_resp = Resp({"jsonrpc": "2.0", "id": 1, "error": {"message": "未找到已发布工具: erp_listing"}})
    with pytest.raises(LingxingMcpError, match="未知工具"):
        _client(fake).action("erp_listing", {})


# ---------------- N13：toolId 一致、白名单只能收窄、_rpc 内部保护 ----------------
@pytest.mark.parametrize("info", [
    {"toolType": "read"},                                   # 缺 toolId
    {"toolId": "get_my_sids", "toolType": "read"},          # 和请求的不一致
])
def test_search_tool_id_missing_or_mismatch_rejected(info):
    fake = FakeLingxing(extra_tools={"erp_listing": info})
    with pytest.raises(LingxingMcpError, match="toolId"):
        _client(fake).action("erp_listing", {})
    assert "action" not in _names(fake)


def test_instance_allowed_tools_cannot_widen():
    fake = FakeLingxing(extra_tools={"update_listing_price": {"toolId": "update_listing_price", "toolType": "read"}})
    c = _client(fake)
    c.allowed_tools = frozenset(set(mc.READ_ONLY_TOOLS) | {"update_listing_price"})
    with pytest.raises(LingxingMcpError, match="只允许只读调用"):
        c.action("update_listing_price", {})
    assert "action" not in _names(fake)


def test_instance_allowed_tools_can_narrow():
    fake = FakeLingxing()
    c = _client(fake)
    c.allowed_tools = frozenset({"get_my_sids"})
    with pytest.raises(LingxingMcpError, match="只允许只读调用"):
        c.action("erp_listing", {})
    c.action("get_my_sids", {})


def test_rpc_direct_action_is_guarded():
    fake = FakeLingxing(extra_tools={"erp_listing": dict(SCHEMAS["erp_listing"], toolType="write")})
    c = _client(fake)
    c.initialize()
    with pytest.raises(LingxingMcpError, match="只允许只读调用"):
        c._rpc("tools/call", {"name": "action", "arguments": {"toolId": "erp_listing", "params": {}}})
    with pytest.raises(LingxingMcpError, match="只允许只读调用"):
        c._rpc("tools/call", {"name": "action", "arguments": {"toolId": "update_listing_price"}})
    assert "action" not in _names(fake)


def test_readonly_constant_is_frozenset():
    assert isinstance(mc.READ_ONLY_TOOLS, frozenset)


# ---------------- N15：search 缓存过期 ----------------
def test_search_cache_expires():
    assert mc.SEARCH_CACHE_TTL_SEC == 600
    fake = FakeLingxing()
    c = _client(fake)
    now = [1000.0]
    c._clock = lambda: now[0]
    c.action("erp_listing", {})
    now[0] += mc.SEARCH_CACHE_TTL_SEC - 1
    c.action("erp_listing", {})
    assert [n for n in _names(fake) if n == "search"] == ["search"]
    now[0] += 2  # 超过 10 分钟
    c.action("erp_listing", {})
    assert [n for n in _names(fake) if n == "search"] == ["search", "search"]


def test_search_cache_expiry_picks_up_type_change():
    fake = FakeLingxing()
    c = _client(fake)
    now = [0.0]
    c._clock = lambda: now[0]
    c.action("erp_listing", {})
    fake.tools["erp_listing"] = dict(SCHEMAS["erp_listing"], toolType="write")
    now[0] += mc.SEARCH_CACHE_TTL_SEC + 1
    with pytest.raises(LingxingMcpError, match="只允许只读调用"):
        c.action("erp_listing", {})
