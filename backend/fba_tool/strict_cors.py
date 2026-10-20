"""只给白名单来源加 CORS 头。未列入的 Origin 不带凭证头。"""
from __future__ import annotations

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class StrictCORSMiddleware:
    def __init__(self, app: ASGIApp, allow_origins: list[str]) -> None:
        self.app = app
        self.allow_origins = set(allow_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        origin = Headers(scope=scope).get("origin")
        allowed = bool(origin) and origin in self.allow_origins
        if scope["method"] == "OPTIONS" and origin:
            if not allowed:
                await send({"type": "http.response.start", "status": 400, "headers": [(b"vary", b"Origin")]})
                await send({"type": "http.response.body", "body": b""})
                return
            headers = [
                (b"access-control-allow-origin", origin.encode("latin-1")),
                (b"access-control-allow-credentials", b"true"),
                (b"access-control-allow-methods", b"GET, POST, PUT, PATCH, DELETE, OPTIONS"),
                (b"access-control-allow-headers", b"*"),
                (b"vary", b"Origin"),
            ]
            await send({"type": "http.response.start", "status": 200, "headers": headers})
            await send({"type": "http.response.body", "body": b"OK"})
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start" and allowed and origin:
                headers = MutableHeaders(scope=message)
                headers["Access-Control-Allow-Origin"] = origin
                headers["Access-Control-Allow-Credentials"] = "true"
                headers.add_vary_header("Origin")
            await send(message)

        await self.app(scope, receive, send_wrapper)
