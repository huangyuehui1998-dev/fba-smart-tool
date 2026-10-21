"""业务数据与代码物理隔离 — 所有可写持久化数据落在 project_root/app_data/。

backend/config/ 与 backend/templates/ 仅为只读出厂默认；用户数据、SQLite、会话、
日志与缓存一律写入 app_data/，与 Git 仓库分离。

数据库结构变更见 backend/docs/数据库安全更新指南.txt
"""
from __future__ import annotations

import shutil
import sys
import os
from pathlib import Path

# 可迁移到 app_data/config/ 的用户配置文件名
_USER_CONFIG_FILES = (
    "user_settings.json",
    "formulas.json",
    "product_catalog.json",
    "sku_mapping.json",
    "fnsku_mapping.json",
    "amazon_sku_metadata.json",
    "invoice_mapping.json",
    "forwarders.json",
    "forwarder_mapping.json",
)


def _backend_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def bundled_backend_dir() -> Path:
    """PyInstaller 包内或开发时的 backend/ 目录（只读默认资源）。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return _backend_dir()


def project_root() -> Path:
    """便携版：exe 所在目录；开发模式：仓库根目录（backend 的上一级）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _backend_dir().parent


def runtime_root() -> Path:
    """向后兼容别名，等同 project_root()。"""
    return project_root()


def _dir_has_data(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(path.iterdir())


def _localappdata_root() -> Path | None:
    base = os.environ.get("LOCALAPPDATA", "").strip()
    if not base:
        return None
    return Path(base)


def tool_state_dir() -> Path | None:
    root = _localappdata_root()
    if root is None:
        return None
    return root / "FBA_Smart_Tool"


def last_data_dir_file() -> Path | None:
    state = tool_state_dir()
    if state is None:
        return None
    return state / "last_data_dir.txt"


def _read_last_data_dir() -> Path | None:
    pointer = last_data_dir_file()
    if pointer is None or not pointer.is_file():
        return None
    text = pointer.read_text(encoding="utf-8").strip()
    return Path(text) if text else None


def _remember_data_dir(path: Path) -> None:
    pointer = last_data_dir_file()
    if pointer is None:
        return
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(str(path.resolve()), encoding="utf-8")


def _exe_has_legacy_payload(root: Path) -> bool:
    return (root / "fba_master.db").is_file() or (root / "config").is_dir()


def app_data_dir() -> Path:
    """数据目录：FBA_APP_DATA_DIR → portable.flag → 已有 app_data 或旧版旁路文件 → %LOCALAPPDATA%。

    没设 LOCALAPPDATA 时（开发机、当前测试）仍用 <程序目录>/app_data，避免写到用户主目录。
    """
    override = os.environ.get("FBA_APP_DATA_DIR", "").strip()
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    root = project_root()
    beside = root / "app_data"
    # 直接双击 exe：数据放在 exe 旁边，和 bat 便携目录一致，不落到 LOCALAPPDATA。
    if getattr(sys, "frozen", False):
        beside.mkdir(parents=True, exist_ok=True)
        return beside
    if (root / "portable.flag").is_file():
        beside.mkdir(parents=True, exist_ok=True)
        return beside
    if _dir_has_data(beside) or _exe_has_legacy_payload(root):
        beside.mkdir(parents=True, exist_ok=True)
        if _dir_has_data(beside):
            _remember_data_dir(beside)
        return beside
    state = tool_state_dir()
    if state is not None:
        path = state / "app_data"
        path.mkdir(parents=True, exist_ok=True)
        remembered = _read_last_data_dir()
        if remembered is not None and remembered.resolve() != path.resolve() and _dir_has_data(remembered) and not _dir_has_data(path):
            return path
        _remember_data_dir(path)
        return path
    beside.mkdir(parents=True, exist_ok=True)
    return beside


def legacy_import_status() -> dict:
    current = app_data_dir()
    remembered = _read_last_data_dir()
    candidate = ""
    if not _dir_has_data(current) and remembered is not None and remembered.resolve() != current.resolve() and _dir_has_data(remembered):
        candidate = str(remembered)
    return {
        "data_dir": str(current),
        "needs_import": bool(candidate),
        "legacy_dir": candidate,
        "message": f"检测到旧数据目录 {candidate}，是否导入" if candidate else "",
    }


def import_legacy_data_dir() -> dict:
    """把旧目录复制到当前数据目录，不移动。"""
    status = legacy_import_status()
    if not status["needs_import"]:
        return {"copied": 0, "legacy_dir": ""}
    source = Path(status["legacy_dir"])
    dest = Path(status["data_dir"])
    copied = 0
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        target = dest / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(path, target)
            copied += 1
    _remember_data_dir(dest)
    return {"copied": copied, "legacy_dir": str(source), "data_dir": str(dest)}


def user_config_dir() -> Path:
    return app_data_dir() / "config"


def user_templates_dir() -> Path:
    return app_data_dir() / "templates"


def sessions_dir() -> Path:
    return app_data_dir() / "sessions"


def logs_dir() -> Path:
    return app_data_dir() / "logs"


def cache_dir() -> Path:
    return app_data_dir() / "cache"


def bundled_config_dir() -> Path:
    return bundled_backend_dir() / "config"


def bundled_templates_dir() -> Path:
    return bundled_backend_dir() / "templates"


def bundled_forwarders_templates_dir() -> Path:
    return bundled_templates_dir() / "forwarders"


def user_forwarders_templates_dir() -> Path:
    return user_templates_dir() / "forwarders"


def master_db_path() -> Path:
    return app_data_dir() / "fba_master.db"


def invoice_history_path() -> Path:
    return app_data_dir() / "invoice_history.json"


def bundled_default(name: str) -> Path:
    """出厂默认：S7 起统一叫 config/<名>.default.json；兼容旧的同名文件。"""
    cfg = bundled_config_dir()
    p = Path(name)
    if not p.stem.endswith(".default"):
        d = cfg / f"{p.stem}.default{p.suffix}"
        if d.is_file():
            return d
    return cfg / name


def resolve_config_read(name: str) -> Path:
    """读取配置：优先 app_data/config，其次 backend/config 出厂默认（<名>.default.json）。"""
    user = user_config_dir() / name
    if user.is_file():
        return user
    return bundled_default(name)


def resolve_config_write(name: str) -> Path:
    """写入配置：始终落在 app_data/config/。"""
    user_config_dir().mkdir(parents=True, exist_ok=True)
    return user_config_dir() / name


def _copy_if_missing(src: Path, dest: Path) -> None:
    if not src.exists() or dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, dest)


def _merge_dir_missing_files(src: Path, dest: Path, skip=None) -> None:
    if not src.is_dir():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            _merge_dir_missing_files(item, target, skip)
        elif skip is not None and skip(item):
            continue
        elif not target.exists():
            shutil.copy2(item, target)


def is_private_template(path: Path) -> bool:
    """D-19：真实产品信息表（文件名含「产品信息表」但不含「示例」）不随安装包发布，也不从出厂模板补进 app_data。"""
    name = Path(path).name
    return "产品信息表" in name and "示例" not in name


LEGACY_MIGRATION_ENV = "FBA_ALLOW_LEGACY_MIGRATION"
_TRUTHY = ("1", "true", "yes", "on")


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _in_test_env() -> bool:
    """pytest 正在跑。S9-step4-fix3：不再看 FBA_NO_BROWSER（打包版用无浏览器模式首次启动时也要正常迁移旧数据）。"""
    return "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))


def legacy_migration_decision() -> tuple:
    """S9-step4-fix2：要不要从旧版路径迁移数据。返回 (是否迁移, 原因)。

    1. 设置了 FBA_APP_DATA_DIR → 一律不迁移（临时 / 自定义数据目录不能混进程序目录里的旧库和会话）。
    2. 测试环境（pytest）→ 一律不迁移。FBA_NO_BROWSER 不影响迁移（S9-step4-fix3）。
    3. 显式开关 FBA_ALLOW_LEGACY_MIGRATION=1 → 迁移（开发模式手动升级旧数据用）。
    4. 打包版 exe（frozen）→ 迁移：老用户把新版解压到旧版目录时，exe 旁的 fba_master.db / config/ 照旧搬进
       <exe 目录>/app_data/；这是正式版的升级路径，保持不变。FBA_ALLOW_LEGACY_MIGRATION=0 可关掉。
    5. 开发模式默认不迁移（仓库里的 backend/fba_master.db、backend/config/sessions/ 是真实数据，不能被复制）。
    """
    if os.environ.get("FBA_APP_DATA_DIR", "").strip():
        return False, "FBA_APP_DATA_DIR"
    if _in_test_env():
        return False, "test_env"
    flag = os.environ.get(LEGACY_MIGRATION_ENV, "").strip().lower()
    if flag in _TRUTHY:
        return True, "explicit"
    if getattr(sys, "frozen", False):
        if flag in ("0", "false", "no", "off"):
            return False, "explicit_off"
        return True, "frozen"
    return False, "dev_default"


def _migrate_legacy_data(app_data: Path) -> None:
    """从旧版路径（backend/ 或 exe 旁 config/）一次性迁移用户数据。只由 ensure_app_data_layout 在
    legacy_migration_decision() 允许时调用。"""
    backend = _backend_dir()
    roots: list[Path] = [project_root()]
    if not getattr(sys, "frozen", False):
        roots.append(backend)

    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve()) if root.exists() else str(root)
        if key in seen:
            continue
        seen.add(key)

        _copy_if_missing(root / "fba_master.db", app_data / "fba_master.db")

        for src_name, dest in (
            (root / "config" / "invoice_history.json", app_data / "invoice_history.json"),
            (root / "invoice_history.json", app_data / "invoice_history.json"),
        ):
            _copy_if_missing(src_name, dest)

        _merge_dir_missing_files(root / "config" / "sessions", app_data / "sessions")
        _merge_dir_missing_files(root / "templates", app_data / "templates")

        for name in _USER_CONFIG_FILES:
            _copy_if_missing(root / "config" / name, app_data / "config" / name)


def _seed_defaults_if_missing(app_data: Path) -> None:
    """首次运行：从出厂默认补齐 app_data 中缺失的配置与历史参考。"""
    bundled_cfg = bundled_config_dir()
    user_cfg = app_data / "config"
    user_cfg.mkdir(parents=True, exist_ok=True)

    for name in _USER_CONFIG_FILES:
        _copy_if_missing(bundled_default(name), user_cfg / name)

    from fba_tool.forwarder_mapping import ensure_forwarder_mapping_seeded

    ensure_forwarder_mapping_seeded()

    _copy_if_missing(bundled_default("invoice_history.json"), app_data / "invoice_history.json")
    _merge_dir_missing_files(bundled_templates_dir(), app_data / "templates", skip=is_private_template)
    _merge_dir_missing_files(bundled_forwarders_templates_dir(), app_data / "templates" / "forwarders", skip=is_private_template)


def ensure_app_data_layout() -> Path:
    """创建 app_data 子目录、迁移旧数据、补齐出厂默认。"""
    ad = app_data_dir()
    if legacy_migration_decision()[0]:
        _migrate_legacy_data(ad)
    _seed_defaults_if_missing(ad)
    for sub in ("config", "templates", "sessions", "logs", "cache"):
        (ad / sub).mkdir(parents=True, exist_ok=True)
    (ad / "sessions" / "history").mkdir(parents=True, exist_ok=True)
    return ad


def ensure_portable_dirs() -> Path:
    """向后兼容别名。"""
    return ensure_app_data_layout()
