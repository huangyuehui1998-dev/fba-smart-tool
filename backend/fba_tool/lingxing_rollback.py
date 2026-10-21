"""确认写入前的数据库备份，以及按这次导入回滚。

回滚只撤销这一次确认写过、且之后没有被别的导入或手改动过的字段。
不把整库还原到备份，所以更早的 run 不会清掉后来的导入和手改。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

from fba_tool.db_backup import backup_file, backups_dir
from fba_tool.lingxing_preview import LingxingPreviewError
from fba_tool.master_db import get_lingxing_sync_run, master_db_path
from fba_tool.master_db_lingxing import set_lingxing_run_file_meta

_SKIP_FIELDS = {
    "sku",
    "updated_at",
    "listing_price_at",
    "regular_price_at",
    "last_nonpromo_at",
    "lingxing_synced_at",
    "invoice_unit",
    "pcs_per_set",
    "purchase_price",
    "purchase_price_currency",
    "material_en",
    "purpose_en",
    "dest_hs_code",
    "fob_unit_value",
    "customs_config_missing",
    "customs_config_status",
}
_SHELL_FIELDS = _SKIP_FIELDS | {"data_source", "field_sources", "field_source_json"}
_COLUMN = {"field_sources": "field_source_json"}


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


def _canon(value: Any) -> str:
    if value in (None, "", [], {}):
        return "null"
    if isinstance(value, float) and value == int(value):
        value = int(value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return json.dumps(value, ensure_ascii=False)


def record_import_changes(run_id: int, sku: str, before: Optional[dict], after: Optional[dict]) -> None:
    """记下这一次确认实际改过的字段。确认事务回滚时，这些记录一起撤销。"""
    if not after:
        return
    before = before or {}
    created = 0 if before else 1
    rows = []
    for field in sorted(set(before) | set(after)):
        if field in _SKIP_FIELDS:
            continue
        old = before.get(field)
        new = after.get(field)
        if _canon(old) == _canon(new):
            continue
        rows.append(
            (
                int(run_id),
                sku,
                field,
                json.dumps(old, ensure_ascii=False),
                json.dumps(new, ensure_ascii=False),
                created,
            )
        )
    if not rows:
        return
    from fba_tool.master_db import _connect

    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO lingxing_import_change
                (run_id, sku, field, old_value, new_value, created_row)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def _assign_field(conn: sqlite3.Connection, sku: str, field: str, value: Any) -> bool:
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(product_master)")}
    column = _COLUMN.get(field, field)
    if column not in columns:
        return False
    # 文本空值写 SQL NULL。原先是 NULL 的列回滚后不能变成 '' 或 '{}'。
    if field == "field_sources":
        payload = None if not value else json.dumps(value, ensure_ascii=False, sort_keys=True)
    elif isinstance(value, str) and not value.strip():
        payload = None
    else:
        payload = value
    conn.execute(f"UPDATE product_master SET {column} = ? WHERE sku = ?", (payload, sku))
    return True


def _empty_shell(product: dict) -> bool:
    for key, value in product.items():
        if key in _SHELL_FIELDS or key == "sku":
            continue
        if _canon(value) != "null":
            return False
    return True


def rollback_lingxing_run(run_id: int) -> dict:
    run = get_lingxing_sync_run(int(run_id))
    if not run:
        raise LingxingPreviewError("找不到该次拉取记录", 404)
    if str(run.get("status") or "") == "rolled_back":
        raise LingxingPreviewError("这次导入已经回滚", 409)
    from fba_tool.master_db import _connect, batch_transaction, delete_product_by_sku, get_product_by_sku
    from fba_tool.master_db_lingxing import mark_lingxing_sync_run_status

    with _connect() as conn:
        own = [
            dict(row)
            for row in conn.execute(
                """
                SELECT sku, field, old_value, new_value, created_row
                FROM lingxing_import_change WHERE run_id = ? ORDER BY id
                """,
                (int(run_id),),
            )
        ]
        later = conn.execute(
            """
            SELECT c.run_id, c.sku, c.field
            FROM lingxing_import_change c
            JOIN lingxing_sync_run r ON r.id = c.run_id
            WHERE c.run_id > ? AND COALESCE(r.status, '') != 'rolled_back'
            """,
            (int(run_id),),
        ).fetchall()
    if not own:
        raise LingxingPreviewError("这次导入没有可回滚的写入", 409)
    later_pairs = {(str(row["sku"]), str(row["field"])) for row in later}
    later_skus = {str(row["sku"]) for row in later}
    later_runs = sorted({int(row["run_id"]) for row in later})
    skipped: list[dict] = []
    reverted: list[dict] = []
    skipped_skus: set[str] = set()
    created_skus = {str(row["sku"]) for row in own if row["created_row"]}

    with batch_transaction():
        for row in own:
            sku = str(row["sku"])
            field = str(row["field"])
            if (sku, field) in later_pairs:
                skipped.append({"sku": sku, "field": field, "reason": "later_run"})
                skipped_skus.add(sku)
                continue
            current = get_product_by_sku(sku)
            if current is None:
                skipped.append({"sku": sku, "field": field, "reason": "missing"})
                continue
            new_value = json.loads(row["new_value"])
            if _canon(current.get(field)) != _canon(new_value):
                skipped.append({"sku": sku, "field": field, "reason": "changed_since"})
                skipped_skus.add(sku)
                continue
            old_value = json.loads(row["old_value"])
            with _connect() as conn:
                if not _assign_field(conn, sku, field, old_value):
                    skipped.append({"sku": sku, "field": field, "reason": "unknown_field"})
                    skipped_skus.add(sku)
                    continue
                conn.commit()
            reverted.append({"sku": sku, "field": field})
        for sku in created_skus:
            if sku in skipped_skus or sku in later_skus:
                continue
            current = get_product_by_sku(sku)
            if current is not None and _empty_shell(current):
                delete_product_by_sku(sku)
        mark_lingxing_sync_run_status(int(run_id), "rolled_back")
    return {
        "ok": True,
        "run_id": int(run_id),
        "reverted": reverted,
        "skipped": skipped,
        "later_runs": later_runs,
    }


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
