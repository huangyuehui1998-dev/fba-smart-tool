"""健康检查。"""
from __future__ import annotations

from fastapi import APIRouter

from fba_tool.app_version import APP_VERSION

router = APIRouter()


@router.get("/api/health")
def health():
    return {"status": "ok", "service": "fba-smart-tool", "version": APP_VERSION, "master_db": True}
