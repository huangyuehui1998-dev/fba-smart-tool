"""健康检查。"""
from __future__ import annotations

from fastapi import APIRouter

from fba_tool.app_version import APP_VERSION

router = APIRouter()


@router.get("/api/health")
def health():
    from fba_tool.app_paths import app_data_dir
    from fba_tool.db_migrations import schema_status

    status = schema_status()
    return {
        "status": "ok",
        "service": "fba-smart-tool",
        "version": APP_VERSION,
        "master_db": True,
        "data_dir": str(app_data_dir()),
        "schema_version": status["schema_version"],
        "carton_spec_count": status["carton_spec_count"],
        "migration_error": status.get("migration_error") or "",
        "readonly": status.get("readonly", False),
    }
