"""V3.2：各处产品版本号一致（界面顶栏、/api/health、打包脚本、spec、启动器、使用说明）。"""
from __future__ import annotations

import re
from pathlib import Path

from fba_tool.app_version import APP_VERSION

ROOT = Path(__file__).resolve().parent.parent


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig")


def test_version_is_v32():
    assert APP_VERSION == "V3.2"


def test_health_reports_version():
    from fastapi.testclient import TestClient
    from main import app

    r = TestClient(app).get("/api/health")
    assert r.status_code == 200 and r.json()["version"] == APP_VERSION and r.json()["status"] == "ok"


def test_release_scripts_use_same_version():
    m = re.search(r'^RELEASE_VERSION = "([^"]+)"', _text("scripts/finish_portable_dist.py"), re.M)
    assert m and m.group(1) == APP_VERSION
    ps1 = _text("scripts/build_standalone.ps1")
    assert f"FBA_Smart_Tool_{APP_VERSION}_便携版" in ps1 and "V3.1" not in ps1


def test_ui_and_docs_show_same_version():
    assert f"U盘便携版 {APP_VERSION}" in _text("frontend/src/components/app-header.tsx")
    assert f"FBA Smart Tool {APP_VERSION} 便携版" in _text("packaging/FBA_Smart_Tool.spec")
    run_app = _text("run_app.py")
    assert run_app.count(f"FBA Smart Tool {APP_VERSION} —") == 2
    readme = _text("packaging/使用说明.txt")
    assert f"FBA Smart Tool {APP_VERSION} — 使用说明" in readme and f"{APP_VERSION} 主要更新" in readme
    for rel in ("frontend/src/components/app-header.tsx", "packaging/FBA_Smart_Tool.spec", "run_app.py", "scripts/finish_portable_dist.py"):
        assert "V3.1" not in _text(rel), rel
