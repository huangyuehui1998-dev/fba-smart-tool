"""S9-step4-fix2：开发 / 测试环境不做旧数据迁移（不把真实 backend/fba_master.db、backend/config/sessions/ 复制进临时
app_data）；打包版 exe 的正式升级路径不变；conftest 护栏能认出真实副本。全部用 tmp_path 里的假“旧版目录”，示例数据。"""
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from fba_tool import app_paths
from realdata_guard import find_real_copies, real_sources

BACKEND = Path(__file__).resolve().parent


def _fake_legacy_root(root: Path) -> Path:
    """造一个“旧版目录”：fba_master.db、config/sessions/、config/user_settings.json（假内容）。"""
    (root / "config" / "sessions" / "history").mkdir(parents=True)
    (root / "fba_master.db").write_bytes(b"FAKE-LEGACY-DB")
    (root / "config" / "sessions" / "autosave.json").write_text('{"task_id": "demo"}', encoding="utf-8")
    (root / "config" / "sessions" / "history" / "demo.json").write_text("{}", encoding="utf-8")
    (root / "config" / "user_settings.json").write_text('{"demo": "legacy"}', encoding="utf-8")
    return root


def _point_legacy_to(monkeypatch, legacy: Path):
    monkeypatch.setattr(app_paths, "project_root", lambda: legacy)
    monkeypatch.setattr(app_paths, "_backend_dir", lambda: legacy)


# ---------------- 设了 FBA_APP_DATA_DIR：不迁移 ----------------

def test_app_data_dir_override_never_migrates(tmp_path, monkeypatch):
    legacy = _fake_legacy_root(tmp_path / "legacy")
    _point_legacy_to(monkeypatch, legacy)
    ad = tmp_path / "ad"
    monkeypatch.setenv("FBA_APP_DATA_DIR", str(ad))
    monkeypatch.setenv(app_paths.LEGACY_MIGRATION_ENV, "1")  # 显式开关也压不过 FBA_APP_DATA_DIR
    monkeypatch.setattr(app_paths, "_in_test_env", lambda: False)
    assert app_paths.legacy_migration_decision() == (False, "FBA_APP_DATA_DIR")
    app_paths.ensure_app_data_layout()
    assert not (ad / "fba_master.db").exists()
    assert list((ad / "sessions").rglob("*.json")) == []
    assert (ad / "config" / "user_settings.json").read_bytes() == app_paths.bundled_default("user_settings.json").read_bytes()


def test_global_test_app_data_has_no_real_copies():
    ad = Path(os.environ["FBA_APP_DATA_DIR"])
    srcs = real_sources(BACKEND, BACKEND.parent)
    assert find_real_copies(ad, srcs) == []
    for s in srcs:
        if s.name == "fba_master.db":
            assert not (ad / "fba_master.db").exists() or (ad / "fba_master.db").stat().st_mtime_ns != s.stat().st_mtime_ns


# ---------------- 决策表 ----------------

def test_pytest_is_test_env():
    assert app_paths._in_test_env() is True


def test_pytest_blocks_even_with_no_browser_and_switch(monkeypatch):
    # S9-step4-fix3：FBA_NO_BROWSER 本身不再算测试环境；这里不迁移是因为 pytest 在跑
    monkeypatch.setenv("FBA_NO_BROWSER", "1")
    assert app_paths._env_truthy("FBA_NO_BROWSER")
    monkeypatch.delenv("FBA_APP_DATA_DIR", raising=False)
    monkeypatch.setenv(app_paths.LEGACY_MIGRATION_ENV, "1")
    assert app_paths.legacy_migration_decision() == (False, "test_env")


@pytest.mark.parametrize("frozen,flag,expected", [
    (False, "", (False, "dev_default")),
    (False, "0", (False, "dev_default")),
    (False, "1", (True, "explicit")),
    (True, "", (True, "frozen")),
    (True, "1", (True, "explicit")),
    (True, "0", (False, "explicit_off")),
])
def test_decision_outside_tests(monkeypatch, frozen, flag, expected):
    monkeypatch.delenv("FBA_APP_DATA_DIR", raising=False)
    monkeypatch.setattr(app_paths, "_in_test_env", lambda: False)
    if flag:
        monkeypatch.setenv(app_paths.LEGACY_MIGRATION_ENV, flag)
    else:
        monkeypatch.delenv(app_paths.LEGACY_MIGRATION_ENV, raising=False)
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    assert app_paths.legacy_migration_decision() == expected


def test_dev_mode_default_does_not_copy(tmp_path, monkeypatch):
    legacy = _fake_legacy_root(tmp_path / "repo")
    _point_legacy_to(monkeypatch, legacy)
    monkeypatch.delenv("FBA_APP_DATA_DIR", raising=False)
    monkeypatch.delenv(app_paths.LEGACY_MIGRATION_ENV, raising=False)
    monkeypatch.setattr(app_paths, "_in_test_env", lambda: False)
    ad = app_paths.ensure_app_data_layout()
    assert ad == legacy / "app_data"
    assert not (ad / "fba_master.db").exists()
    assert not (ad / "sessions" / "autosave.json").exists()


# ---------------- 打包版 exe：正式升级路径不变 ----------------

def _fake_frozen(monkeypatch, exe_dir: Path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "FBA_Smart_Tool.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(BACKEND), raising=False)  # 出厂默认从仓库 backend/ 读（只读）
    monkeypatch.delenv("FBA_APP_DATA_DIR", raising=False)
    monkeypatch.delenv(app_paths.LEGACY_MIGRATION_ENV, raising=False)
    monkeypatch.setattr(app_paths, "_in_test_env", lambda: False)


def test_frozen_exe_upgrade_migrates_old_layout(tmp_path, monkeypatch):
    exe_dir = _fake_legacy_root(tmp_path / "portable")
    _fake_frozen(monkeypatch, exe_dir)
    assert app_paths.project_root() == exe_dir
    ad = app_paths.ensure_app_data_layout()
    assert ad == exe_dir / "app_data"
    assert (ad / "fba_master.db").read_bytes() == b"FAKE-LEGACY-DB"
    assert (ad / "sessions" / "autosave.json").is_file()
    assert (ad / "sessions" / "history" / "demo.json").is_file()
    assert (ad / "config" / "user_settings.json").read_text(encoding="utf-8") == '{"demo": "legacy"}'
    # 再启动一次：已有数据不被旧目录覆盖
    (ad / "fba_master.db").write_bytes(b"NEWER")
    app_paths.ensure_app_data_layout()
    assert (ad / "fba_master.db").read_bytes() == b"NEWER"
    # 冻结模式只看 exe 目录，不碰仓库 backend/
    assert app_paths._backend_dir() == BACKEND


def test_frozen_exe_with_temp_app_data_does_not_migrate(tmp_path, monkeypatch):
    exe_dir = _fake_legacy_root(tmp_path / "portable")
    _fake_frozen(monkeypatch, exe_dir)
    ad = tmp_path / "exe_ad"
    monkeypatch.setenv("FBA_APP_DATA_DIR", str(ad))
    app_paths.ensure_app_data_layout()
    assert not (ad / "fba_master.db").exists()
    assert not (ad / "sessions" / "autosave.json").exists()


def test_frozen_explicit_off(tmp_path, monkeypatch):
    exe_dir = _fake_legacy_root(tmp_path / "portable")
    _fake_frozen(monkeypatch, exe_dir)
    monkeypatch.setenv(app_paths.LEGACY_MIGRATION_ENV, "0")
    ad = app_paths.ensure_app_data_layout()
    assert not (ad / "fba_master.db").exists()


# ---------------- 护栏本身 ----------------

def test_guard_detects_copy2_of_real_source(tmp_path):
    real = _fake_legacy_root(tmp_path / "real")
    srcs = real_sources(real, tmp_path / "noroot")
    assert {p.name for p in srcs} == {"fba_master.db", "autosave.json", "demo.json"}
    ad = tmp_path / "ad"
    (ad / "sessions").mkdir(parents=True)
    assert find_real_copies(ad, srcs) == []
    shutil.copy2(real / "fba_master.db", ad / "fba_master.db")
    shutil.copytree(real / "config" / "sessions", ad / "sessions", dirs_exist_ok=True)
    found = find_real_copies(ad, srcs)
    assert sorted(f.split(":")[0] for f in found) == ["fba_master.db", "sessions/autosave.json", "sessions/history/demo.json"]


def test_guard_content_only_old_mtime_alone_not_flagged(tmp_path):
    # S9-step4-fix3：改为按内容比对；修改时间旧但内容不是真实来源的文件不算副本（不误报）
    real = _fake_legacy_root(tmp_path / "real")
    ad = tmp_path / "ad"
    (ad / "sessions").mkdir(parents=True)
    old = ad / "sessions" / "x.json"
    old.write_text('{"note": "test-only"}', encoding="utf-8")
    os.utime(old, (time.time() - 3600, time.time() - 3600))
    assert find_real_copies(ad, real_sources(real, tmp_path / "noroot")) == []
