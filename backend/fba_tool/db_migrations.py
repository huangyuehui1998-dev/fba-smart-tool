"""主库迁移。只加不删。当前最新 user_version = 4。"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Callable, List, Optional, Tuple

from fba_tool.db_backup import backup_daily, backup_migration, integrity_ok, utc_now
from fba_tool.sku_keys import sku_key

LATEST_VERSION = 4
Migration = Tuple[int, Callable[[sqlite3.Connection], None]]

_MIGRATION_ERROR: dict[str, str] = {}


class MigrationFailed(RuntimeError):
    """升级失败，数据未改动。"""


def migration_error(path: str = "") -> str:
    return _MIGRATION_ERROR.get(path, "")


def record_migration_error(path: str, message: str) -> None:
    _MIGRATION_ERROR[path] = message


def clear_migration_error(path: str) -> None:
    _MIGRATION_ERROR.pop(path, None)


def read_user_version(path) -> int:
    from pathlib import Path

    file = Path(path)
    if not file.is_file():
        return 0
    uri = "file:" + file.resolve().as_posix() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def is_readonly(path=None) -> bool:
    from fba_tool.app_paths import master_db_path

    file = path or master_db_path()
    try:
        return read_user_version(file) > LATEST_VERSION
    except sqlite3.Error:
        return False


def user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def create_v4_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS carton_spec (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku_key TEXT NOT NULL,
            sku TEXT NOT NULL,
            spec_name TEXT NOT NULL,
            version INTEGER NOT NULL,
            length_cm REAL,
            width_cm REAL,
            height_cm REAL,
            qty_per_carton INTEGER,
            tare_kg REAL,
            gross_kg REAL,
            unit_kg REAL,
            status TEXT NOT NULL,
            is_default INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL,
            source_ref TEXT,
            note TEXT,
            valid_from TEXT,
            valid_to TEXT,
            created_at TEXT NOT NULL,
            created_by TEXT,
            UNIQUE(sku_key, spec_name, version)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS carton_spec_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            carton_spec_id INTEGER,
            sku_key TEXT,
            sku TEXT,
            action TEXT NOT NULL,
            before_json TEXT,
            after_json TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS shipment_box_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fba_id TEXT NOT NULL,
            task_id TEXT,
            batch TEXT,
            box_no INTEGER,
            fba_box_id TEXT NOT NULL,
            carton_spec_id INTEGER,
            sku_items_json TEXT,
            length_cm REAL,
            width_cm REAL,
            height_cm REAL,
            gross_kg REAL,
            declared_to_amazon_json TEXT,
            stage TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(fba_id, fba_box_id, stage)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS carton_measurement (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fba_id TEXT,
            fba_box_id TEXT,
            box_no INTEGER,
            sku_key TEXT,
            measured_by TEXT,
            length_cm REAL,
            width_cm REAL,
            height_cm REAL,
            weight_kg REAL,
            chargeable_kg REAL,
            raw_unit TEXT,
            raw_json TEXT,
            source_file TEXT,
            source_row INTEGER,
            measured_at TEXT,
            imported_at TEXT,
            import_batch_id TEXT,
            match_status TEXT,
            manual_box_id TEXT,
            content_hash TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS item_measurement (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT,
            asin TEXT,
            marketplace TEXT,
            longest_cm REAL,
            median_cm REAL,
            shortest_cm REAL,
            weight_kg REAL,
            size_tier_amazon TEXT,
            raw_json TEXT,
            source_file TEXT,
            report_date TEXT,
            imported_at TEXT,
            import_batch_id TEXT,
            content_hash TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS forwarder_bill (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fba_id TEXT,
            forwarder TEXT,
            bill_chargeable_kg REAL,
            channel_min_kg REAL,
            source_file TEXT,
            imported_at TEXT,
            import_batch_id TEXT
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_carton_spec_sku ON carton_spec(sku_key, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_carton_measure_batch ON carton_measurement(import_batch_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_item_measure_batch ON item_measurement(import_batch_id)")


def _has_carton(row: sqlite3.Row) -> bool:
    keys = set(row.keys())
    for name in ("carton_length", "carton_width", "carton_height", "qty_per_box", "carton_gross_weight", "carton_weight"):
        if name in keys and row[name] not in (None, ""):
            return True
    return False


def _copy_product_cartons(conn: sqlite3.Connection) -> None:
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "product_master" not in tables:
        return
    now = utc_now()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM product_master").fetchall()
    for row in rows:
        if not _has_carton(row):
            continue
        sku = str(row["sku"])
        qty = row["qty_per_box"] if "qty_per_box" in row.keys() else None
        spec_name = f"装量{int(qty)}" if qty not in (None, "") else "默认"
        payload = {
            "sku": sku,
            "spec_name": spec_name,
            "version": 1,
            "length_cm": row["carton_length"] if "carton_length" in row.keys() else None,
            "width_cm": row["carton_width"] if "carton_width" in row.keys() else None,
            "height_cm": row["carton_height"] if "carton_height" in row.keys() else None,
            "qty_per_carton": int(qty) if qty not in (None, "") else None,
            "tare_kg": row["carton_weight"] if "carton_weight" in row.keys() else None,
            "gross_kg": row["carton_gross_weight"] if "carton_gross_weight" in row.keys() else None,
            "source": "migrated_v3",
        }
        conn.execute(
            """INSERT OR IGNORE INTO carton_spec (
                sku_key, sku, spec_name, version, length_cm, width_cm, height_cm, qty_per_carton,
                tare_kg, gross_kg, unit_kg, status, is_default, source, source_ref, note,
                valid_from, valid_to, created_at, created_by
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                sku_key(sku), sku, spec_name, 1,
                payload["length_cm"], payload["width_cm"], payload["height_cm"], payload["qty_per_carton"],
                payload["tare_kg"], payload["gross_kg"], None,
                "active", 1, "migrated_v3", "product_master", "",
                now, None, now, "migration",
            ),
        )
        spec_id = conn.execute(
            "SELECT id FROM carton_spec WHERE sku_key=? AND spec_name=? AND version=1",
            (sku_key(sku), spec_name),
        ).fetchone()[0]
        conn.execute(
            """INSERT INTO carton_spec_history (carton_spec_id, sku_key, sku, action, before_json, after_json, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (spec_id, sku_key(sku), sku, "create", None, json.dumps(payload, ensure_ascii=False), now),
        )


def _expand_ticket_boxes(conn: sqlite3.Connection) -> None:
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "shipment_ticket" not in tables:
        return
    now = utc_now()
    conn.row_factory = sqlite3.Row
    tickets = conn.execute("SELECT fba_id, batch, boxes_json FROM shipment_ticket").fetchall()
    for ticket in tickets:
        try:
            boxes = json.loads(ticket["boxes_json"] or "[]")
        except json.JSONDecodeError:
            continue
        for index, box in enumerate(boxes, start=1):
            box_id = str(box.get("box_no") or box.get("fba_box_id") or "")
            conn.execute(
                """INSERT INTO carton_measurement (
                    fba_id, fba_box_id, box_no, sku_key, measured_by, length_cm, width_cm, height_cm,
                    weight_kg, chargeable_kg, raw_unit, raw_json, source_file, source_row, measured_at,
                    imported_at, import_batch_id, match_status, content_hash
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ticket["fba_id"], box_id, index, "", "forwarder_jiufang",
                    box.get("length"), box.get("width"), box.get("height"),
                    box.get("weight"), box.get("chargeable_kg"), "as_imported",
                    json.dumps(box, ensure_ascii=False), "shipment_ticket.boxes_json", index,
                    None, now, f"migrate-{ticket['fba_id']}", "", f"ticket:{ticket['fba_id']}:{box_id}:{index}",
                ),
            )


def migrate_v4_carton_lib(conn: sqlite3.Connection) -> None:
    steps = (
        ("create_tables", create_v4_tables),
        ("copy_specs", _copy_product_cartons),
        ("expand_measurements", _expand_ticket_boxes),
    )
    fail_at = os.environ.get("FBA_MIGRATION_FAIL_STEP", "").strip()
    for index, (_name, fn) in enumerate(steps, start=1):
        if fail_at == str(index):
            raise MigrationFailed("升级失败，数据未改动")
        fn(conn)


MIGRATIONS: List[Migration] = [(4, migrate_v4_carton_lib)]


def run_migrations(conn: sqlite3.Connection, db_path: str = "") -> int:
    """按 user_version 依次执行。每一步一个事务。失败则回滚并保留原版本。"""
    if os.environ.get("FBA_SKIP_MIGRATION", "").strip() in {"1", "true", "yes"}:
        return user_version(conn)
    version = user_version(conn)
    if version > LATEST_VERSION:
        return version
    for target, fn in MIGRATIONS:
        if version >= target:
            continue
        conn.commit()
        backup_migration(version, target, conn)
        # 默认 isolation_level="" 时 DDL 会自动提交，回滚撤不掉新表。显式事务才能整步撤销。
        previous_isolation = conn.isolation_level
        conn.isolation_level = "DEFERRED"
        try:
            conn.execute("BEGIN")
            fn(conn)
            conn.execute(f"PRAGMA user_version = {int(target)}")
            conn.commit()
            version = target
            clear_migration_error(db_path)
        except Exception as exc:
            conn.rollback()
            message = str(exc) if isinstance(exc, MigrationFailed) else "升级失败，数据未改动"
            record_migration_error(db_path, message)
            raise MigrationFailed(message) from exc
        finally:
            conn.isolation_level = previous_isolation
    backup_daily(conn)
    return version


def schema_status(path=None) -> dict:
    from fba_tool.app_paths import app_data_dir, master_db_path

    file = path or master_db_path()
    version = read_user_version(file) if file.is_file() else 0
    count = 0
    integrity = "missing"
    if file.is_file():
        integrity = "ok" if integrity_ok(file) else "fail"
        if version <= LATEST_VERSION:
            conn = sqlite3.connect(file)
            try:
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if "carton_spec" in tables:
                    count = int(conn.execute("SELECT COUNT(*) FROM carton_spec").fetchone()[0])
            finally:
                conn.close()
    return {
        "data_dir": str(app_data_dir()),
        "schema_version": version,
        "carton_spec_count": count,
        "integrity": integrity,
        "readonly": version > LATEST_VERSION,
        "migration_error": migration_error(str(file)),
        "supported_version": LATEST_VERSION,
    }


def skus_with_carton(conn: sqlite3.Connection) -> int:
    conn.row_factory = sqlite3.Row
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "product_master" not in tables:
        return 0
    return sum(1 for row in conn.execute("SELECT * FROM product_master") if _has_carton(row))
