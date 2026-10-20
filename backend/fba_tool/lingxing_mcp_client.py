"""领星官方 MCP Streamable HTTP 客户端。

桌面软件自己发 HTTP，不走 Cursor Agent 的 MCP 工具。
协议：JSON-RPC over HTTP（响应可能是 SSE，data: 开头的行），initialize → tools/call，请求头 X-Mcp-Key，
服务端返回的 Mcp-Session-Id 会在后续请求里带上。
领星 MCP 只暴露 help / search / action 三个元工具（S9-step1 按 2026-10-16 实测适配）：
- help()：不带参数，返回工具列表；**列表可能不全**（实测 erp_listing 不在 help 里，但 search 能查到），所以不以 help 为准。
- search(toolId)：参数 {"toolId": ...}，返回 data 里有 toolType（read / write）和 inputSchema；未知工具返回 code=102、success=false。
- action(toolId, params)：参数 {"toolId": ..., "params": {...}}。
安全：每次 action 前先 search 同一 toolId（结果按 toolId 缓存），只有 toolType == "read" 且 toolId 在 READ_ONLY_TOOLS
白名单里才放行，其他一律拒绝并报错（错误文字含“只允许只读调用”，定时同步按不可恢复处理）。
返回：content[0].text 里的 JSON，常见两层信封 {code:1, data:{code:1, msg, data:{total, list}}}；旧的一层格式也兼容。
官方限制 QPS=1，所有请求串行且间隔 ≥1s。
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import requests

DEFAULT_MCP_URL = "https://openmcp.lingxing.com/mcp-servers/lingxing-mcp"
DEFAULT_MIN_INTERVAL_SEC = 1.05
REQUEST_TIMEOUT_SEC = 60
MCP_PROTOCOL_VERSION = "2024-11-05"

# 只读白名单（2026-10-16 用 search 实测：6 个 toolId 在新接口里名字不变，toolType 都是 read）
READ_ONLY_TOOLS = frozenset({
    "get_my_sids",
    "get_multi_platform_shop_list",
    "erp_listing",
    "get_fba_stock_list",
    "query_fba_valid_list",
    "query_product_performance_asin_lists",
})
TOOL_TYPE_READ = "read"
SEARCH_CACHE_TTL_SEC = 600  # S9-step1-fix N15：search 结果缓存 10 分钟，过期重新 search
UNKNOWN_TOOL_CODES = (102, "102")
UNKNOWN_TOOL_TEXT = "未找到已发布工具"


class LingxingMcpError(RuntimeError):
    """MCP 传输或领星业务错误。code 为领星返回的业务码（有的话）。
    fatal=True 的子类表示“重试也不会好”，定时同步据此（按异常类型，不看文字）决定不重试（S9-step2 M3）。"""

    fatal = False

    def __init__(self, message: str, code: Any = None) -> None:
        super().__init__(message)
        self.code = code


class LingxingUnknownToolError(LingxingMcpError):
    """search 返回 code=102（未找到已发布工具）。"""
    fatal = True


class LingxingReadOnlyError(LingxingMcpError):
    """只读保护拒绝：不在白名单、toolType 不是 read、未知 method / 工具名、参数不合法。"""
    fatal = True


class LingxingAuthError(LingxingMcpError):
    """鉴权或账号失败（不重试）。判定规则见 is_auth_failure（S9-step3：信封、HTTP、JSON-RPC 三条通道同一个函数）；
    另外未配置 Key 也归这一类。"""
    fatal = True


def is_fatal_exception(exc: BaseException) -> bool:
    """按异常类型判断是否不可恢复（不对服务端原文做子串匹配）。"""
    return bool(getattr(exc, "fatal", False))


# 领星 Key 无效时 tools/call 返回 isError，没有业务码，只能认这段固定提示（2026-10-16 实测原文的开头）。
# 只在 isError 分支、且只认开头，避免把限流等文字误判为鉴权失败。
_AUTH_ISERROR_PREFIX = "MCP Key无效或已失效"
# S9-step3 #4：鉴权 / 账号失败（不重试）的判定，信封、HTTP、JSON-RPC（含 tools/call isError）三条通道都用 is_auth_failure，按顺序：
# 1. 文字以领星鉴权原文“MCP Key无效或已失效”开头 → 鉴权失败（优先于限流词）；
# 2. 文字含“禁用 / 封禁 / disabled / banned” → 账号被禁用或封禁，按鉴权/账号错误处理，不重试；
# 3. 码是 401 → 鉴权失败；码是 403 → 鉴权失败，但文字是限流（见 _RATE_LIMIT_WORDS）时可重试（N5）；
# 4. 业务码 102 且文字含“Key无效” → 鉴权失败（信封旧写法）。
# 其余（含单独出现的“Key无效”字样、普通限流 429）都按普通错误处理，可以重试。
# 限流词只认具体短语，不再用宽泛的“频繁”（“账号因频繁违规已被禁用”这类封禁文字不能被当成限流重试）。
_AUTH_TEXT = "Key无效"
_RATE_LIMIT_WORDS = (
    "rate limit", "ratelimit", "rate-limit", "rate limited", "too many requests", "throttl",
    "请求过于频繁", "请求太频繁", "访问太频繁", "访问过于频繁", "调用过于频繁", "调用太频繁", "操作过于频繁", "限流",
)
_BANNED_WORDS = ("禁用", "封禁", "disabled", "banned")


def _is_auth_text(msg: Any) -> bool:
    return _AUTH_TEXT in str(msg or "").replace(" ", "")


def _is_auth_prefix(msg: Any) -> bool:
    return str(msg or "").strip().startswith(_AUTH_ISERROR_PREFIX)


def _is_rate_limit_text(msg: Any) -> bool:
    low = str(msg or "").lower()
    return any(w in low for w in _RATE_LIMIT_WORDS)


def _is_banned_text(msg: Any) -> bool:
    low = str(msg or "").lower()
    return any(w in low for w in _BANNED_WORDS)


def is_auth_failure(code: Any, msg: Any) -> bool:
    """S9-step3：三条通道共用的鉴权 / 账号失败判定（规则见上面注释）。code 可以是信封业务码、HTTP 状态码或 JSON-RPC 错误码。"""
    if _is_auth_prefix(msg):
        return True
    if _is_banned_text(msg):
        return True
    if code in (401, "401"):
        return True
    if code in (403, "403"):
        return not _is_rate_limit_text(msg)
    if code in UNKNOWN_TOOL_CODES and _is_auth_text(msg):
        return True
    return False
ALLOWED_METHODS = frozenset({"initialize", "notifications/initialized", "tools/call"})
ALLOWED_META_TOOLS = frozenset({"help", "search", "action"})


_OK_CODES = (1, "1")


def _fail(env: Dict[str, Any], default: str = "领星接口失败") -> None:
    msg = env.get("msg") or env.get("message") or default
    details = env.get("error_details")
    if details:
        msg = f"{msg}（{details}）"
    code = env.get("code")
    text = f"{msg}（code={code}）" if "code" in env else str(msg)
    if is_auth_failure(code, msg):
        raise LingxingAuthError(text, code=code)  # 信封通道
    raise LingxingMcpError(text, code=code)


def _check_envelope(env: Dict[str, Any], level: str) -> None:
    """S9-step1-fix N14：信封校验。有 code 就必须是 1；没有 code 的旧格式按 success 判断；data 不能是字符串。"""
    if "code" in env:
        if env.get("code") not in _OK_CODES:
            _fail(env, f"领星接口失败（{level}）")
        if "success" in env and env.get("success") is not True:  # M2：必须恰好是布尔 True
            _fail(env, f"领星接口失败（{level}）")
    elif "success" in env:
        if env.get("success") is not True:
            _fail(env, f"领星接口失败（{level}）")
    if isinstance(env.get("data"), str) and ("code" in env or "success" in env):
        raise LingxingMcpError(f"领星返回格式异常：{level} data 是字符串（{env.get('data')[:80]}）", code=env.get("code"))


def parse_sse_json_objects(text: str) -> List[Any]:
    """从 text/event-stream 正文解析 JSON-RPC 对象。"""
    objects: List[Any] = []
    data_lines: List[str] = []

    def flush() -> None:
        if not data_lines:
            return
        raw = "\n".join(data_lines).strip()
        data_lines.clear()
        if not raw:
            return
        try:
            objects.append(json.loads(raw))
        except json.JSONDecodeError:
            return

    for line in str(text or "").splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif not line.strip():
            flush()
    flush()
    return objects


def unwrap_lingxing_payload(payload: Any) -> Any:
    """解包 MCP tools/call 结果与领星信封（可重复调用，结果不变）。
    S9-step1-fix N14：原则是 code≠1 或不是 JSON 就报错，不再把失败静默当成“成功 0 行”：
    外层 code 为 0/102 等（无论有没有 success 键）、内层 code≠1（含 500 无 data、0 带 data）、content 不是 JSON、
    data 是字符串，一律 LingxingMcpError。没有 code 键的旧一层格式按 success 判断。"""
    if payload is None:
        return None
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            raise LingxingMcpError(f"领星返回不是 JSON：{text[:120]}")

    if isinstance(payload, dict) and "jsonrpc" in payload:
        if payload.get("error"):
            err = payload["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            ecode = err.get("code") if isinstance(err, dict) else None
            if is_auth_failure(ecode, msg):
                raise LingxingAuthError(f"MCP 错误：{msg}", code=ecode)  # JSON-RPC 通道
            raise LingxingMcpError(f"MCP 错误：{msg}")  # 不带 code：保持 S9-step1-fix 的“未知工具”文字判断不变
        payload = payload.get("result", payload)

    if isinstance(payload, dict) and "content" in payload:
        if payload.get("isError"):
            msg = _content_text(payload) or "MCP 工具返回 isError"
            if is_auth_failure(None, msg):
                raise LingxingAuthError(msg)  # JSON-RPC tools/call isError
            raise LingxingMcpError(msg)
        text = _content_text(payload)
        if text:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                raise LingxingMcpError(f"领星返回的 content 不是 JSON：{text[:120]}")
        elif "structuredContent" in payload:
            payload = payload["structuredContent"]
        else:
            raise LingxingMcpError("领星返回的 content 为空")

    if isinstance(payload, dict) and ("code" in payload or "success" in payload):
        _check_envelope(payload, "外层")
        inner = payload.get("data")
        if isinstance(inner, dict) and ("code" in inner or "success" in inner):
            _check_envelope(inner, "内层")
    return payload


def extract_list(payload: Any) -> List[Dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("list", "data", "records", "items"):
        val = data.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
        if isinstance(val, dict):
            inner = val.get("list") or val.get("data") or val.get("records")
            if isinstance(inner, list):
                return [x for x in inner if isinstance(x, dict)]
    return []


def extract_total(payload: Any, fallback: int = 0) -> int:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        for key in ("total", "total_count", "count"):
            if isinstance(data.get(key), (int, float)):
                return int(data[key])
        inner = data.get("data")
        if isinstance(inner, dict):
            for key in ("total", "total_count", "count"):
                if isinstance(inner.get(key), (int, float)):
                    return int(inner[key])
    return fallback


def _content_text(result: Dict[str, Any]) -> str:
    content = result.get("content")
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text") or ""))
    return "\n".join(parts).strip()


def pick_field(row: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return default


class LingxingMcpClient:
    def __init__(
        self,
        mcp_key: str,
        mcp_url: str = DEFAULT_MCP_URL,
        min_interval: float = DEFAULT_MIN_INTERVAL_SEC,
        session: Optional[requests.Session] = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        key = str(mcp_key or "").strip()
        if not key:
            raise LingxingAuthError("未配置领星 MCP Key")
        self.mcp_key = key
        self.mcp_url = str(mcp_url or DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL
        self.min_interval = max(1.0, float(min_interval))
        self._session = session or requests.Session()
        self._sleeper = sleeper
        self._last_call = 0.0
        self._rpc_id = 0
        self._session_id = ""
        self._initialized = False
        self._tool_info: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._clock: Callable[[], float] = time.monotonic
        # 只能收窄：最终放行要求同时在模块常量 READ_ONLY_TOOLS 和这里（N13）
        self.allowed_tools = frozenset(READ_ONLY_TOOLS)

    def initialize(self) -> Any:
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "fba-smart-tool", "version": "1.2.0"},
            },
        )
        try:
            self._rpc("notifications/initialized", None, notification=True)
        except LingxingMcpError:
            pass
        self._initialized = True
        return result

    def search(self, tool_id: str) -> Dict[str, Any]:
        """查工具元数据（toolType、inputSchema 等），按 toolId 缓存 SEARCH_CACHE_TTL_SEC 秒。
        只有 code=102 或“未找到已发布工具”才报“未知工具”（定时同步按不可恢复处理）；
        限流、非 JSON、空 SSE、网络错误等原样抛出（可重试），都不会放行 action（N12）。"""
        tool_id = str(tool_id or "").strip()
        cached = self._tool_info.get(tool_id)
        if cached and self._clock() - cached[0] < SEARCH_CACHE_TTL_SEC:
            return cached[1]
        self._tool_info.pop(tool_id, None)
        self._ensure_initialized()
        try:
            payload = self._rpc("tools/call", {"name": "search", "arguments": {"toolId": tool_id}})
        except LingxingAuthError:
            raise  # M4：Key 无效优先于“未知工具”（102+Key无效 归鉴权失败）
        except LingxingMcpError as exc:
            # M3：有业务码就只认 102；没有业务码时才看“未找到已发布工具”（例如 429 文字里带这几个字也可重试）
            if exc.code in UNKNOWN_TOOL_CODES or (exc.code is None and UNKNOWN_TOOL_TEXT in str(exc)):
                raise LingxingUnknownToolError(f"领星 MCP 未知工具 {tool_id}：{exc}", code=exc.code) from exc
            raise
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or not data.get("toolType"):
            raise LingxingMcpError(f"领星 MCP search {tool_id} 返回格式异常：没有 toolType，拒绝调用")
        if str(data.get("toolId") or "").strip() != tool_id:
            raise LingxingMcpError(
                f"领星 MCP search {tool_id} 返回的 toolId 缺失或不一致（{data.get('toolId')!r}），拒绝调用")
        self._tool_info[tool_id] = (self._clock(), data)
        return data

    def _authorize(self, tool_id: str) -> None:
        # N13：直接对照模块级不可变常量；实例 allowed_tools 只能再收窄，不能扩大
        if tool_id not in READ_ONLY_TOOLS or tool_id not in self.allowed_tools:
            raise LingxingReadOnlyError(f"只允许只读调用：{tool_id} 不在只读白名单 READ_ONLY_TOOLS 里，已拒绝")
        info = self.search(tool_id)
        tool_type = str(info.get("toolType") or "").strip().lower()
        if tool_type != TOOL_TYPE_READ:
            raise LingxingReadOnlyError(f"只允许只读调用：{tool_id} 的 toolType={tool_type or '空'}，不是 read，已拒绝")

    def action(self, tool_id: str, params: Optional[Dict[str, Any]] = None) -> Any:
        tool_id = str(tool_id or "").strip()
        self._ensure_initialized()
        # 校验在 _rpc 里统一做（任何 tools/call name=action 都先 search 确认 read + 白名单）
        payload = self._rpc(
            "tools/call",
            {
                "name": "action",
                "arguments": {"toolId": tool_id, "params": params or {}},
            },
        )
        return unwrap_lingxing_payload(payload)

    def help(self) -> Any:
        self._ensure_initialized()
        payload = self._rpc("tools/call", {"name": "help", "arguments": {}})
        return unwrap_lingxing_payload(payload)

    def iter_pages(
        self,
        tool_id: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        offset_key: str = "offset",
        length_key: str = "length",
        page_size: int = 50,
        start_offset: int = 1,
    ) -> Iterator[Tuple[int, List[Dict[str, Any]], int]]:
        """分页拉取。yield (offset, rows, total)。领星多数接口 offset 为从 0 起的行偏移。"""
        offset = int(start_offset)
        total = 0
        collected = 0
        while True:
            body = dict(params or {})
            body[offset_key] = offset
            body[length_key] = int(page_size)
            payload = self.action(tool_id, body)
            rows = extract_list(payload)
            total = extract_total(payload, fallback=total or (collected + len(rows)))
            collected += len(rows)
            yield offset, rows, total
            if not rows:
                break
            if total and collected >= total:
                break
            if len(rows) < page_size:
                break
            offset += max(len(rows), int(page_size))
            if offset > 100_000:
                break

    def paginate(
        self,
        tool_id: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        offset_key: str = "offset",
        length_key: str = "length",
        page_size: int = 50,
        start_offset: int = 1,
        on_page: Optional[Callable[[int, int, int, List[Dict[str, Any]]], None]] = None,
    ) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        for offset, rows, total in self.iter_pages(
            tool_id,
            params,
            offset_key=offset_key,
            length_key=length_key,
            page_size=page_size,
            start_offset=start_offset,
        ):
            collected.extend(rows)
            if on_page:
                on_page(offset, len(collected), total, rows)
        return collected

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self.initialize()

    def _next_id(self) -> int:
        self._rpc_id += 1
        return self._rpc_id

    def _throttle(self) -> None:
        now = time.monotonic()
        wait = self.min_interval - (now - self._last_call)
        if wait > 0:
            self._sleeper(wait)
        self._last_call = time.monotonic()

    def _rpc(
        self,
        method: str,
        params: Any,
        *,
        notification: bool = False,
    ) -> Any:
        method, params = self._normalize_call(method, params)
        self._throttle()
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not notification:
            payload["id"] = self._next_id()
        if params is not None:
            payload["params"] = params
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-Mcp-Key": self.mcp_key,
            "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        try:
            resp = self._session.post(
                self.mcp_url,
                headers=headers,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                timeout=REQUEST_TIMEOUT_SEC,
            )
        except requests.RequestException as exc:
            raise LingxingMcpError(f"领星 MCP 网络错误：{exc}") from exc

        session_id = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
        if session_id:
            self._session_id = session_id

        if resp.status_code >= 400:
            text = (resp.text or "").strip()[:400]
            cls = LingxingAuthError if is_auth_failure(resp.status_code, text) else LingxingMcpError  # HTTP 通道
            raise cls(f"领星 MCP HTTP {resp.status_code}：{text or resp.reason}", code=resp.status_code)

        if notification:
            return None
        return unwrap_lingxing_payload(self._decode_response(resp))

    def _normalize_call(self, method: Any, params: Any) -> Tuple[str, Any]:
        """M1：只放行已知 method 和元工具名；先 strip + lower 再判断，发出去的用整理后的值。
        tools/call 的 params 必须是 dict、arguments 必须是 dict；name=action 时 toolId 去空白后走只读校验（N13）。"""
        m = str(method or "").strip().lower()
        if m not in ALLOWED_METHODS:
            raise LingxingReadOnlyError(f"只允许只读调用：未知 method {method!r}，已拒绝")
        if m != "tools/call":
            return m, params
        if not isinstance(params, dict):
            raise LingxingReadOnlyError(f"只允许只读调用：tools/call 的 params 必须是对象，收到 {type(params).__name__}")
        name = str(params.get("name") or "").strip().lower()
        if name not in ALLOWED_META_TOOLS:
            raise LingxingReadOnlyError(f"只允许只读调用：未知工具名 {params.get('name')!r}，已拒绝")
        args = params.get("arguments", {})
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise LingxingReadOnlyError(f"只允许只读调用：arguments 必须是对象，收到 {type(args).__name__}")
        args = dict(args)
        if "toolId" in args or name in ("search", "action"):
            args["toolId"] = str(args.get("toolId") or "").strip()
        if name == "action":
            if "params" in args and args["params"] is not None and not isinstance(args["params"], dict):
                raise LingxingReadOnlyError("只允许只读调用：action 的 params 必须是对象")
            self._authorize(args["toolId"])  # N13：内部保护，绕过 action() 也要校验
        out = dict(params)
        out["name"] = name
        out["arguments"] = args
        return m, out

    def _decode_response(self, resp: requests.Response) -> Any:
        ctype = (resp.headers.get("Content-Type") or "").lower()
        text = resp.text or ""
        if "text/event-stream" in ctype or text.lstrip().startswith("event:") or "\ndata:" in text:
            objects = parse_sse_json_objects(text)
            if not objects:
                raise LingxingMcpError("领星 MCP SSE 响应为空")
            return objects[-1]
        if not text.strip():
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LingxingMcpError(f"领星 MCP 响应不是 JSON：{text[:200]}") from exc
