"""fba_master.db 备份。WAL 下用 sqlite3.Connection.backup()，不直接拷文件。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fba_tool.app_paths import app_data_dir, master_db_path

DAILY_KEEP = 14
MIGRATION_KEEP = 10
IMPORT_KEEP = 10


def backups_dir() -> Path:
    path = app_data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _today() -> str:
    return datetime.now().strftime("%Y%m%d")


def backup_connection(conn: sqlite3.Connection, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    target = sqlite3.connect(dest)
    try:
        conn.backup(target)
    finally:
        target.close()
    return dest


def backup_file(source: Optional[Path] = None, dest: Optional[Path] = None) -> Path:
    src = source or master_db_path()
    if dest is None:
        raise ValueError("dest is required")
    if not src.is_file():
        raise FileNotFoundError(src)
    origin = sqlite3.connect(src)
    try:
        return backup_connection(origin, dest)
    finally:
        origin.close()


def _prune(pattern: str, keep: int) -> None:
    files = sorted(backups_dir().glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)


def backup_migration(old_version: int, new_version: int, conn: Optional[sqlite3.Connection] = None) -> Path:
    dest = backups_dir() / f"fba_master.v{old_version}_to_v{new_version}.{_stamp()}.db"
    if conn is not None:
        backup_connection(conn, dest)
    else:
        backup_file(dest=dest)
    _prune("fba_master.v*_to_v*.db", MIGRATION_KEEP)
    return dest


def backup_daily(conn: Optional[sqlite3.Connection] = None) -> Optional[Path]:
    dest = backups_dir() / f"fba_master.daily.{_today()}.db"
    if dest.is_file():
        return None
    if conn is not None:
        backup_connection(conn, dest)
    else:
        if not master_db_path().is_file():
            return None
        backup_file(dest=dest)
    _prune("fba_master.daily.*.db", DAILY_KEEP)
    return dest


def backup_reason(reason: str, conn: Optional[sqlite3.Connection] = None) -> Path:
    dest = backups_dir() / f"fba_master.{reason}.{_stamp()}.db"
    if conn is not None:
        backup_connection(conn, dest)
    else:
        backup_file(dest=dest)
    _prune(f"fba_master.{reason}.*.db", IMPORT_KEEP)
    return dest


def integrity_ok(path: Path) -> bool:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return bool(row) and row[0] == "ok"
    finally:
        conn.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
