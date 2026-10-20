"""S7 工程整理验收（v8 §3.8）：config/*.default.json 统一、Streamlit 归档、依赖锁定、冒烟脚本存在。"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[2]
ROOT = HERE.parent
CFG = HERE / "config"

# 规则配置：只读出厂、用户可在 app_data/config 放同名文件覆盖（不是用户数据，不改名）
RULE_CONFIGS = {"invoice_template_map.json", "lingxing_field_map.json", "ticket_import_map.json", "fba_warehouse_corrections.json"}


def test_bundled_user_configs_are_all_default_json():
    from fba_tool.app_paths import _USER_CONFIG_FILES
    plain = sorted(p.name for p in CFG.glob("*.json") if not p.name.endswith(".default.json") and p.name not in RULE_CONFIGS)
    assert plain == [], f"出厂配置应叫 *.default.json：{plain}"
    for name in _USER_CONFIG_FILES:
        if name == "product_catalog.json":
            continue
        assert (CFG / name.replace(".json", ".default.json")).is_file(), name


def test_read_falls_back_to_default_and_writes_go_to_app_data(tmp_path, monkeypatch):
    from fba_tool import app_paths
    ad = tmp_path / "ad"
    monkeypatch.setattr(app_paths, "app_data_dir", lambda: ad)
    assert app_paths.resolve_config_read("formulas.json") == CFG / "formulas.default.json"
    assert app_paths.resolve_config_read("forwarders.json") == CFG / "forwarders.default.json"
    assert app_paths.resolve_config_read("invoice_template_map.json") == CFG / "invoice_template_map.json"
    w = app_paths.resolve_config_write("formulas.json")
    assert w == ad / "config" / "formulas.json"
    w.write_text("{}", encoding="utf-8")
    assert app_paths.resolve_config_read("formulas.json") == w


def test_first_run_seeds_app_data_from_defaults(tmp_path, monkeypatch):
    from fba_tool import app_paths
    ad = tmp_path / "ad"
    monkeypatch.setattr(app_paths, "app_data_dir", lambda: ad)
    monkeypatch.setattr(app_paths, "project_root", lambda: tmp_path / "nolegacy")
    app_paths.ensure_app_data_layout()
    for name in ("user_settings.json", "formulas.json", "sku_mapping.json", "fnsku_mapping.json",
                 "amazon_sku_metadata.json", "invoice_mapping.json", "forwarders.json", "forwarder_mapping.json"):
        assert (ad / "config" / name).is_file(), name
    assert (ad / "invoice_history.json").is_file()
    assert (ad / "config" / "formulas.json").read_bytes() == (CFG / "formulas.default.json").read_bytes()


def test_streamlit_archived_and_not_required():
    assert not (HERE / "app.py").exists()
    assert not (HERE / "legacy_streamlit").exists()
    live = [p for p in list(HERE.glob("*.py")) + list((HERE / "fba_tool").glob("*.py")) + list((HERE / "routers").glob("*.py"))
            if re.search(r"^\s*(import|from)\s+streamlit", p.read_text(encoding="utf-8"), re.M)]
    assert live == []
    assert "streamlit" not in (HERE / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "streamlit" not in _names(HERE / "requirements.lock.txt")


def _names(path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        m = re.match(r"([A-Za-z0-9_.\-]+)(\[[^\]]+\])?\s*(==|>=|<=|~=)?\s*([^;\s]*)", line)
        out[m.group(1).lower().replace("_", "-")] = (m.group(3), m.group(4))
    return out


def test_requirements_lock_pins_every_requirement():
    req = _names(HERE / "requirements.txt")
    lock = _names(HERE / "requirements.lock.txt")
    assert all(op == "==" for op, _ in lock.values()), "lock 里每个包都要 == 锁死"
    missing = [n for n in req if n not in lock]
    assert missing == []
    dev = _names(HERE / "requirements-dev.lock.txt")
    assert {"pytest", "httpx", "pyinstaller"} <= set(dev)


def test_smoke_script_and_user_manual_exist():
    assert (ROOT / "scripts" / "smoke_e2e.py").is_file()
    txt = (ROOT / "docs" / "使用说明.md").read_text(encoding="utf-8")
    for k in ("产品库", "发票", "报关"):
        assert k in txt
