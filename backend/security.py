"""S1d 访问安全：默认只监听本机；可选访问口令。

环境变量：
- FBA_HOST：监听地址，默认 127.0.0.1。设成非本机地址时必须同时设置 FBA_ACCESS_TOKEN，否则拒绝启动。
- FBA_ACCESS_TOKEN：访问口令，默认不启用。启用后 /api/*（/api/health、/api/auth/login 除外）
  需要请求头 X-Access-Token 或登录得到的 cookie。

登录只接受 POST /api/auth/login（JSON {"token": "..."} 或表单 token=...）。
口令不进 URL，避免出现在浏览器历史和访问日志里。GET 登录返回 405。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

COOKIE_NAME = "fba_session"
HEADER_NAME = "X-Access-Token"
SESSION_TTL_SECONDS = 12 * 60 * 60
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}
_EXEMPT = {"/api/health", "/api/auth/login"}


def bind_host() -> str:
    return (os.environ.get("FBA_HOST") or "127.0.0.1").strip()


def access_token() -> Optional[str]:
    tok = (os.environ.get("FBA_ACCESS_TOKEN") or "").strip()
    return tok or None


def is_loopback(host: str) -> bool:
    h = (host or "").strip().lower()
    return h in _LOOPBACK or h.startswith("127.")


def check_bind_safety(host: str, token: Optional[str]) -> None:
    if not is_loopback(host) and not (token or "").strip():
        raise RuntimeError(
            f"拒绝启动：监听地址 {host} 不是本机地址，但未设置访问口令 FBA_ACCESS_TOKEN。"
        )


def _ok(given: Optional[str], token: str) -> bool:
    return bool(given) and hmac.compare_digest(given.encode("utf-8"), token.encode("utf-8"))


def issue_session_value(token: str, now: Optional[int] = None) -> str:
    """cookie 值是过期时间加 HMAC，不包含口令原文。"""
    exp = int(now if now is not None else time.time()) + SESSION_TTL_SECONDS
    mac = hmac.new(token.encode("utf-8"), str(exp).encode("utf-8"), hashlib.sha256).hexdigest()
    value = f"{exp}.{mac}"
    if token and token in value:
        raise RuntimeError("会话 cookie 包含了口令原文")
    return value


def session_is_valid(value: Optional[str], token: str, now: Optional[int] = None) -> bool:
    if not value or "." not in value or token in value:
        return False
    exp_text, mac = value.split(".", 1)
    try:
        exp = int(exp_text)
    except ValueError:
        return False
    current = int(now if now is not None else time.time())
    if exp <= current:
        return False
    expected = hmac.new(token.encode("utf-8"), exp_text.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, expected)


def install_access_control(app: FastAPI) -> None:
    """注册登录端点与口令中间件。口令在安装时读取；未设置则不拦截。"""
    token = access_token()

    def _login_response(given: Optional[str], redirect: bool):
        if token is None:
            return JSONResponse({"ok": True, "enabled": False})
        if not _ok(given, token):
            return JSONResponse({"detail": {"message": "访问口令错误"}}, status_code=401)
        resp = RedirectResponse("/", status_code=303) if redirect else JSONResponse({"ok": True, "enabled": True})
        resp.set_cookie(
            COOKIE_NAME,
            issue_session_value(token),
            httponly=True,
            samesite="strict",
            max_age=SESSION_TTL_SECONDS,
        )
        return resp

    @app.post("/api/auth/login", include_in_schema=False)
    async def _login_post(request: Request):
        ctype = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in ctype or "multipart/form-data" in ctype:
            form = await request.form()
            return _login_response(str(form.get("token") or ""), redirect=True)
        try:
            body = await request.json()
        except Exception:
            body = {}
        return _login_response((body or {}).get("token"), redirect=False)

    @app.api_route("/api/auth/login", methods=["GET"], include_in_schema=False)
    async def _login_get():
        return JSONResponse({"detail": "GET 登录已关闭，请用 POST"}, status_code=405)

    if token is None:
        return

    @app.middleware("http")
    async def _guard(request: Request, call_next):
        path = request.url.path
        if (
            request.method == "OPTIONS"
            or not path.startswith("/api/")
            or path in _EXEMPT
        ):
            return await call_next(request)
        header = request.headers.get(HEADER_NAME)
        cookie = request.cookies.get(COOKIE_NAME)
        if _ok(header, token) or session_is_valid(cookie, token):
            return await call_next(request)
        return JSONResponse(
            {"detail": {"message": "需要访问口令：请 POST /api/auth/login"}},
            status_code=401,
        )


# ---- S2-7：访问日志屏蔽 ?token= ----
import logging as _logging
import re as _re

_TOKEN_RE = _re.compile(r"((?:^|[?&\s])token=)[^&\s\"']*", _re.IGNORECASE)


def _mask(value):
    return _TOKEN_RE.sub(r"\1***", value) if isinstance(value, str) else value


class TokenMaskFilter(_logging.Filter):
    """把日志中 URL 查询参数 token=xxx 改写为 token=***。"""

    def filter(self, record: _logging.LogRecord) -> bool:
        record.msg = _mask(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_mask(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: _mask(v) for k, v in record.args.items()}
        return True


def install_token_log_filter() -> None:
    for name in ("uvicorn.access", "uvicorn.error"):
        lg = _logging.getLogger(name)
        if not any(isinstance(f, TokenMaskFilter) for f in lg.filters):
            lg.addFilter(TokenMaskFilter())


install_token_log_filter()
