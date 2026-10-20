"""V3.2：各处产品版本号一致（界面顶栏、/api/health、打包脚本、spec、启动器、使用说明）。"""
from __future__ import annotations

import re
from pathlib import Path

from fba_tool.app_version import APP_VERSION

ROOT = Path(__file__).resolve().parents[3]


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig")


def test_version_is_v32():
    assert APP_VERSION == "V3.2"


def test_health_reports_version():
    from fastapi.testclient import TestClient
    from main import app

    r = TestClient(app).get("/api/health")
    assert r.status_code == 200 and r.json()["version"] == APP_VERSION and r.json()["status"] == "ok"


def test_version_is_defined_once():
    hits = []
    for path in (ROOT / "backend").rglob("*.py"):
        if "legacy_streamlit" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r'^APP_VERSION\s*=\s*"', text, re.M):
            hits.append(path.relative_to(ROOT).as_posix())
    assert hits == ["backend/fba_tool/app_version.py"]


def test_release_scripts_use_same_version():
    import importlib.util

    path = ROOT / "scripts" / "finish_portable_dist.py"
    spec = importlib.util.spec_from_file_location("finish_portable_dist", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.RELEASE_VERSION == APP_VERSION
    ps1 = _text("scripts/build_standalone.ps1")
    assert "app_version.py" in ps1 and "V3.1" not in ps1
    assert 'APP_VERSION = "([^"]+)"' in ps1


def test_ui_and_docs_show_same_version():
    assert f"U盘便携版 {APP_VERSION}" in _text("frontend/src/components/app-header.tsx")
    assert f"FBA Smart Tool {APP_VERSION} 便携版" in _text("packaging/FBA_Smart_Tool.spec")
    run_app = _text("run_app.py")
    assert "from fba_tool.app_version import APP_VERSION" in run_app
    assert 'f"  FBA Smart Tool {APP_VERSION} — 一键启动"' in run_app
    readme = _text("packaging/使用说明.txt")
    assert f"FBA Smart Tool {APP_VERSION} — 使用说明" in readme and f"{APP_VERSION} 主要更新" in readme
    for rel in ("frontend/src/components/app-header.tsx", "packaging/FBA_Smart_Tool.spec", "run_app.py", "scripts/finish_portable_dist.py"):
        assert "V3.1" not in _text(rel), rel
