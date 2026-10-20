"""S1d 访问安全：默认只监听本机；可选访问口令。

环境变量：
- FBA_HOST：监听地址，默认 127.0.0.1。设成非本机地址（如 0.0.0.0）时必须同时设置 FBA_ACCESS_TOKEN，否则拒绝启动。
- FBA_ACCESS_TOKEN：访问口令，默认不启用。启用后 /api/*（/api/health、/api/auth/login 除外）
  需要请求头 X-Access-Token 或登录得到的 cookie。

登录方式（任选其一，登录后写入 HttpOnly cookie，前端无需改动）：
1. 推荐：浏览器打开 /api/auth/login（不带参数），在页面输入口令提交（POST，口令不进 URL）；
   脚本可 POST /api/auth/login，JSON {"token": "..."} 或表单 token=...。
2. 兼容：GET /api/auth/login?token=口令。
   ⚠ 注意：URL 方式会让口令出现在浏览器历史、uvicorn 访问日志和代理日志里，
   可能被记录下来；只建议在本机临时使用，优先用 POST。
"""
from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

COOKIE_NAME = "fba_access"
HEADER_NAME = "X-Access-Token"
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}
_EXEMPT = {"/api/health", "/api/auth/login"}


_LOGIN_PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>FBA 助手登录</title></head>
<body style="font-family:sans-serif;max-width:360px;margin:80px auto">
<h3>请输入访问口令</h3>
<form method="post" action="/api/auth/login">
<input type="password" name="token" autofocus style="width:100%;padding:8px" autocomplete="current-password">
<button type="submit" style="margin-top:12px;padding:8px 16px">登录</button>
</form></body></html>"""


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


def install_access_control(app: FastAPI) -> None:
    """注册登录端点与口令中间件。口令在安装时读取；未设置则不拦截。"""
    token = access_token()

    def _login_response(given: Optional[str], redirect: bool):
        if token is None:
            return JSONResponse({"ok": True, "enabled": False})
        if not _ok(given, token):
            return JSONResponse({"detail": {"message": "访问口令错误"}}, status_code=401)
        resp = RedirectResponse("/", status_code=303) if redirect else JSONResponse({"ok": True, "enabled": True})
        resp.set_cookie(COOKIE_NAME, token, httponly=True, samesite="strict")
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

    @app.get("/api/auth/login", include_in_schema=False)
    async def _login_get(token: str = ""):
        if not token:
            return HTMLResponse(_LOGIN_PAGE)
        # 兼容 URL 传口令；口令可能进入访问日志，推荐用页面 POST
        return _login_response(token, redirect=True)

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
        given = request.headers.get(HEADER_NAME) or request.cookies.get(COOKIE_NAME)
        if not _ok(given, token):
            return JSONResponse(
                {"detail": {"message": "需要访问口令：请先在浏览器打开 /api/auth/login 输入口令"}},
                status_code=401,
            )
        return await call_next(request)


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
