"""
FBA 智能装箱工具 — FastAPI 后端入口。

应用工厂 + 路由装配。业务逻辑见 routers/ (路由) · services/ (编排) · fba_tool/ (核心)。

启动：uvicorn main:app --reload --host 127.0.0.1 --port 8000
（默认只监听本机；对外监听须设置 FBA_HOST 与 FBA_ACCESS_TOKEN，见 security.py）
"""
from __future__ import annotations

import logging
import os
import sys

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse, Response

from fba_tool.app_paths import ensure_app_data_layout
from fba_tool.master_db import init_master_db
from fba_tool.strict_cors import StrictCORSMiddleware
from security import install_access_control
from settings import CORS_ALLOW_ORIGINS

from routers.health import router as health_router
from routers.config import router as config_router
from routers.master_data import router as master_data_router
from routers.tasks import router as tasks_router
from routers.step1 import router as step1_router
from routers.boxing import router as boxing_router
from routers.export_step3 import router as export_step3_router
from routers.shipment import router as shipment_router
from routers.pdf_tools import router as pdf_tools_router
from routers.routing import router as routing_router
from routers.invoice import router as invoice_router
from routers.forwarders import router as forwarders_router
from routers.customs import router as customs_router
from routers.lingxing import router as lingxing_router
from routers.tickets import router as tickets_router
from routers.invoice_templates import router as invoice_templates_router
from routers.invoice_export import router as invoice_export_router
from routers.carton import router as carton_router

logger = logging.getLogger(__name__)

_ROUTERS = (
    health_router,
    config_router,
    master_data_router,
    tasks_router,
    step1_router,
    boxing_router,
    export_step3_router,
    shipment_router,
    pdf_tools_router,
    invoice_router,
    forwarders_router,
    customs_router,
    routing_router,
    lingxing_router,
    tickets_router,
    invoice_templates_router,
    invoice_export_router,
    carton_router,
)


def _frontend_dist_dir() -> str:
    """PyInstaller 打包后资源在 sys._MEIPASS/dist；开发环境在 backend/dist。"""
    if getattr(sys, "frozen", False):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "dist")


def _resolve_index_html(frontend_dist: str) -> str:
    index_path = os.path.join(frontend_dist, "index.html")
    if os.path.isfile(index_path):
        return index_path
    shell_path = os.path.join(frontend_dist, "_shell.html")
    if os.path.isfile(shell_path):
        return shell_path
    raise FileNotFoundError(f"未找到 index.html / _shell.html：{frontend_dist}")


class _AssetStaticFiles(StaticFiles):
    """带正确 MIME 与缓存头的静态资源（避免旧版误缓存 HTML 当 JS）。"""

    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            suffix = os.path.splitext(path)[1].lower()
            if suffix == ".js":
                response.headers["Content-Type"] = "application/javascript; charset=utf-8"
            elif suffix == ".css":
                response.headers["Content-Type"] = "text/css; charset=utf-8"
            if suffix in (".js", ".css", ".woff", ".woff2", ".png", ".svg", ".ico"):
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def _mount_frontend_spa(app: FastAPI) -> None:
    """挂载顺序：须在全部 /api/* 路由注册之后调用。"""
    frontend_dist = _frontend_dist_dir()
    if not os.path.isdir(frontend_dist):
        msg = f"未找到前端目录 {frontend_dist}"
        if getattr(sys, "frozen", False):
            raise RuntimeError(
                f"{msg}。请重新打包（npm run build && python scripts/sync_frontend_static.py）。"
            )
        logger.info("%s，跳过静态挂载（开发模式可单独跑 Vite）。", msg)
        return

    try:
        index_path = _resolve_index_html(frontend_dist)
    except FileNotFoundError as exc:
        if getattr(sys, "frozen", False):
            raise RuntimeError(str(exc)) from exc
        logger.info("%s，跳过静态挂载。", exc)
        return

    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.isdir(assets_dir):
        app.mount(
            "/assets",
            _AssetStaticFiles(directory=assets_dir),
            name="assets",
        )

    @app.get("/", include_in_schema=False)
    async def serve_index_root():
        return FileResponse(
            index_path,
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/{catchall:path}", include_in_schema=False)
    async def serve_spa(catchall: str):
        if catchall.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        if catchall.startswith("assets/"):
            raise HTTPException(status_code=404, detail="Asset not found")
        if catchall in ("docs", "redoc", "openapi.json"):
            raise HTTPException(status_code=404, detail="Not Found")
        # 带点号的路径视为静态资源；找不到则 404，避免把 index.html 当 JS/CSS 返回
        if "." in catchall:
            candidate = os.path.join(frontend_dist, catchall)
            if os.path.isfile(candidate):
                return FileResponse(candidate)
            raise HTTPException(status_code=404, detail="Asset not found")
        return FileResponse(
            index_path,
            headers={"Cache-Control": "no-cache"},
        )

    logger.info("已挂载前端 SPA：%s", frontend_dist)


def create_app() -> FastAPI:
    from security import access_token, bind_host, check_bind_safety

    check_bind_safety(bind_host(), access_token())
    from fba_tool.log_redact import install_redacting_logs

    install_redacting_logs()
    ensure_app_data_layout()
    init_master_db()
    try:
        from fba_tool.catalog_seed import import_catalog_gaps_into_master

        import_catalog_gaps_into_master()
    except Exception:
        logger.exception("产品信息表.csv 空字段灌入主库失败（运行时仍只读 SQLite）")

    app = FastAPI(
        title="FBA Smart Tool API",
        description="亚马逊 FBA 智能装箱与货件处理后端",
        version="1.2.0",
    )

    app.add_middleware(StrictCORSMiddleware, allow_origins=CORS_ALLOW_ORIGINS)

    install_access_control(app)

    @app.middleware("http")
    async def reject_unsafe_history_ids(request, call_next):
        from fba_tool.history_guard import history_task_suffix, safe_history_path

        raw = request.scope.get("raw_path") or b""
        text = raw.decode("latin-1", "replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
        suffix = history_task_suffix(text or request.url.path)
        if suffix:
            try:
                safe_history_path(suffix)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": {"code": "INVALID_TASK_ID", "message": "任务编号不合法"}},
                )
        return await call_next(request)

    @app.middleware("http")
    async def reject_writes_when_db_is_newer(request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/"):
            from fba_tool.db_migrations import is_readonly

            if is_readonly():
                return JSONResponse(
                    status_code=409,
                    content={"code": "DB_NEWER_THAN_APP", "message": "数据库版本高于当前程序，已只读打开"},
                )
        return await call_next(request)

    for router in _ROUTERS:
        app.include_router(router)

    _mount_frontend_spa(app)

    # S5：领星定时同步（asyncio 后台任务，默认关闭；FBA_DISABLE_SCHEDULER=1 时不启动）
    async def _start_scheduler() -> None:
        if os.environ.get("FBA_DISABLE_SCHEDULER") != "1":
            from fba_tool import lingxing_scheduler

            lingxing_scheduler.start()

    async def _stop_scheduler() -> None:
        from fba_tool import lingxing_scheduler

        await lingxing_scheduler.stop()

    app.router.on_startup.append(_start_scheduler)
    app.router.on_shutdown.append(_stop_scheduler)

    return app

app = create_app()


if __name__ == "__main__":
    import uvicorn

    from security import bind_host

    uvicorn.run("main:app", host=bind_host(), port=int(os.environ.get("FBA_PORT", "8000")), reload=True)
