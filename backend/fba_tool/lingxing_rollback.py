"""确认写入前的数据库备份，以及按这次导入回滚。"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from fba_tool.db_backup import backup_file, backups_dir
from fba_tool.lingxing_preview import LingxingPreviewError
from fba_tool.master_db import get_lingxing_sync_run, master_db_path
from fba_tool.master_db_lingxing import set_lingxing_run_file_meta


def backup_before_confirm(run_id: int) -> Optional[str]:
    run = get_lingxing_sync_run(int(run_id)) or {}
    if str(run.get("trigger") or "") != "xlsx_import":
        return None
    existing = str(run.get("backup_path") or "")
    if existing and Path(existing).is_file():
        return existing
    # 按 run 单独落盘。按秒命名的通用备份会在同一秒内的第二次确认时互相覆盖。
    path = backups_dir() / f"fba_master.lingxing_xlsx.run{int(run_id)}.db"
    backup_file(dest=path)
    set_lingxing_run_file_meta(int(run_id), backup_path=str(path))
    return str(path)


def rollback_lingxing_run(run_id: int) -> dict:
    run = get_lingxing_sync_run(int(run_id))
    if not run:
        raise LingxingPreviewError("找不到该次拉取记录", 404)
    backup = str(run.get("backup_path") or "")
    if not backup or not Path(backup).is_file():
        raise LingxingPreviewError("这次导入没有可回滚的备份", 409)
    restore_sqlite(Path(backup), master_db_path())
    return {"ok": True, "run_id": int(run_id), "restored_from": backup}


def restore_sqlite(backup: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        live = sqlite3.connect(dest)
        try:
            live.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            live.close()
    src = sqlite3.connect(f"file:{backup}?mode=ro", uri=True)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
        dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        dst.commit()
    finally:
        dst.close()
        src.close()
    for suffix in ("-wal", "-shm"):
        extra = Path(str(dest) + suffix)
        if extra.is_file():
            extra.unlink()
