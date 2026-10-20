"""S9-step1：领星 MCP 新接口（help / search / action）协议层 mock 测试。
fixture 来自 2026-10-16 真实接口（search 只留 schema；action 响应已脱敏、只 1 行；未知工具响应去掉 traceId）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fba_tool.lingxing_mcp_client import (
    READ_ONLY_TOOLS,
    LingxingMcpClient,
    LingxingMcpError,
    extract_list,
    extract_total,
    unwrap_lingxing_payload,
)

FIX = Path(__file__).parent / "tests" / "fixtures" / "lingxing"
SCHEMAS = json.loads((FIX / "mcp_search_schemas.json").read_text(encoding="utf-8"))["tools"]
ACTION = json.loads((FIX / "mcp_action_erp_listing_sanitized.json").read_text(encoding="utf-8"))
UNKNOWN = json.loads((FIX / "mcp_search_unknown.json").read_text(encoding="utf-8"))


def _text_result(obj, rid=1):
    return {"jsonrpc": "2.0", "id": rid,
            "result": {"content": [{"type": "text", "text": json.dumps(obj, ensure_ascii=False)}], "isError": False}}


class Resp:
    def __init__(self, obj, sse=True, session_id=None):
        self.status_code = 200
        self.reason = "OK"
        body = json.dumps(obj, ensure_ascii=False)
        if sse:
            self.headers = {"Content-Type": "text/event-stream"}
            self.text = "event: message\ndata: " + body + "\n\n"
        else:
            self.headers = {"Content-Type": "application/json"}
            self.text = body
        if session_id:
            self.headers["Mcp-Session-Id"] = session_id


class FakeLingxing:
    """按真实接口行为模拟：initialize 发会话 ID；search 查 SCHEMAS（可替换/增加工具）；action 返回脱敏 fixture。"""

    def __init__(self, extra_tools=None, sse=True):
        self.tools = dict(SCHEMAS)
        self.tools.update(extra_tools or {})
        self.sse = sse
        self.log = []  # (method, name, toolId, Mcp-Session-Id, X-Mcp-Key)

    def post(self, url, headers=None, data=None, timeout=None):
        raw = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
        method = raw.get("method")
        params = raw.get("params") or {}
        args = params.get("arguments") or {}
        h = headers or {}
        self.log.append((method, params.get("name"), args.get("toolId"), h.get("Mcp-Session-Id"), h.get("X-Mcp-Key")))
        rid = raw.get("id", 0)
        if method == "initialize":
            return Resp({"jsonrpc": "2.0", "id": rid, "result": {"protocolVersion": "2024-11-05", "capabilities": {}}},
                        sse=self.sse, session_id="sess-abc")
        if method == "notifications/initialized":
            return Resp({}, sse=False)
        name = params.get("name")
        if name == "help":
            return Resp(_text_result({"code": 1, "success": True, "data": {
                "usage": "", "total": 1, "tools": [{"toolId": "get_my_sids", "toolType": "read"}]}}, rid), sse=self.sse)
        if name == "search":
            tid = args.get("toolId")
            if tid not in self.tools:
                return Resp(dict(UNKNOWN, id=rid), sse=self.sse)
            return Resp(_text_result({"code": 1, "success": True, "msg": "操作成功", "data": self.tools[tid]}, rid),
                        sse=self.sse)
        if name == "action":
            return Resp(dict(ACTION, id=rid), sse=self.sse)
        raise AssertionError("意外请求 %r" % raw)


def _client(fake):
    return LingxingMcpClient("fake-key-for-test", session=fake, min_interval=1.0, sleeper=lambda s: None)


def _names(fake):
    return [n for _m, n, *_r in fake.log]


def test_whitelist_matches_search_fixture_all_read():
    assert set(SCHEMAS) == set(READ_ONLY_TOOLS)
    assert all(v["toolType"] == "read" and v["toolId"] == k for k, v in SCHEMAS.items())
    assert "properties" in SCHEMAS["erp_listing"]["inputSchema"]


def test_sse_session_id_and_search_before_action():
    fake = FakeLingxing(sse=True)
    c = _client(fake)
    payload = c.action("erp_listing", {"offset": 0, "length": 3, "pvi_ids": "", "fulfillment_channel_type": "FBA"})
    calls = [(n, t) for m, n, t, _s, _k in fake.log if m == "tools/call"]
    assert calls == [("search", "erp_listing"), ("action", "erp_listing")]
    after_init = [s for m, _n, _t, s, _k in fake.log if m != "initialize"]
    assert after_init and all(s == "sess-abc" for s in after_init)  # 会话 ID 之后每个请求都带
    assert all(k == "fake-key-for-test" for *_x, k in fake.log)
    rows = extract_list(payload)
    assert extract_total(payload) == 1 and rows[0]["msku"] == "DEMO-MSKU-001-FBA"
    assert rows[0]["regular_price"] == rows[0]["listing_price"] == "15.99"


def test_plain_json_response_also_works_and_search_cached():
    fake = FakeLingxing(sse=False)
    c = _client(fake)
    c.action("erp_listing", {})
    c.action("erp_listing", {})
    c.action("get_my_sids", {})
    assert [t for _m, n, t, _s, _k in fake.log if n == "search"] == ["erp_listing", "get_my_sids"]
    assert c.search("erp_listing")["toolType"] == "read"


def test_write_tool_rejected_even_if_whitelisted():
    fake = FakeLingxing(extra_tools={"erp_listing": dict(SCHEMAS["erp_listing"], toolType="write")})
    c = _client(fake)
    with pytest.raises(LingxingMcpError, match="只允许只读调用"):
        c.action("erp_listing", {})
    assert "action" not in _names(fake)


def test_not_in_whitelist_rejected_without_calling_action():
    fake = FakeLingxing(extra_tools={"update_listing_price": {"toolId": "update_listing_price", "toolType": "read"}})
    c = _client(fake)
    with pytest.raises(LingxingMcpError, match="只允许只读调用"):
        c.action("update_listing_price", {})
    assert "search" not in _names(fake) and "action" not in _names(fake)


def test_unknown_tool_raises():
    fake = FakeLingxing()
    fake.tools.pop("get_fba_stock_list")
    c = _client(fake)
    with pytest.raises(LingxingMcpError, match="未知工具"):
        c.action("get_fba_stock_list", {})
    assert "action" not in _names(fake)


def test_unknown_and_readonly_errors_are_fatal_for_scheduler():
    from fba_tool.lingxing_scheduler import READ_ONLY_TOOLS as SCHED_TOOLS, is_fatal_error

    from fba_tool.lingxing_mcp_client import LingxingReadOnlyError, LingxingUnknownToolError

    assert SCHED_TOOLS is READ_ONLY_TOOLS
    assert is_fatal_error(LingxingUnknownToolError("领星 MCP 未知工具 x：未找到已发布工具: x", code=102))
    assert is_fatal_error(LingxingReadOnlyError("只允许只读调用：x 的 toolType=write，不是 read，已拒绝"))


def test_two_level_envelope_and_legacy_one_level():
    two = unwrap_lingxing_payload(ACTION)
    assert extract_total(two) == 1 and len(extract_list(two)) == 1
    one = unwrap_lingxing_payload(_text_result({"success": True, "code": 1, "data": {"list": [{"a": 1}], "total": 1}}))
    assert extract_list(one) == [{"a": 1}] and extract_total(one) == 1
    bare = unwrap_lingxing_payload(_text_result({"code": 1, "data": [{"a": 2}]}))
    assert extract_list(bare) == [{"a": 2}]


def test_inner_failure_raises():
    bad = _text_result({"code": 1, "success": True, "data": {"code": 0, "msg": "内层失败", "data": None}})
    with pytest.raises(LingxingMcpError, match="内层失败"):
        unwrap_lingxing_payload(bad)
    bad2 = _text_result({"code": 1, "success": True, "data": {"success": False, "msg": "内层拒绝"}})
    with pytest.raises(LingxingMcpError, match="内层拒绝"):
        unwrap_lingxing_payload(bad2)


def test_help_list_incomplete_does_not_block_search():
    fake = FakeLingxing()
    c = _client(fake)
    tools = c.help()["data"]["tools"]
    assert "erp_listing" not in {t["toolId"] for t in tools}  # 和实测一样：help 里没有
    assert c.search("erp_listing")["toolType"] == "read"     # 但 search 能查到


def test_fixtures_have_no_sensitive_fields():
    text = (FIX / "mcp_action_erp_listing_sanitized.json").read_text(encoding="utf-8")
    for k in ("seller_name", "principal", "store_id", '"sid"', "shop", "traceId", '"mid"', "request_id"):
        assert k not in text, k
    assert "traceId" not in UNKNOWN["result"]["content"][0]["text"]
