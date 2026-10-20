"""SQLite 产品主数据库 product_master。

持久化路径：<project_root>/app_data/fba_master.db（见 app_paths.py）

字段语义：
- unit_*   单品尺寸/重量（Fee Preview，带包装）→ 仅用于入库配置费
- carton_* 外箱尺寸/重量（运营维护 / 包装规则库）→ 用于 Step1 CBM、排箱、货代
- chinese_name → 商品报关名称（发票/报关）
- model_name   → 中文名称(型号)（工人实操单、发货表）
- hs_code / ... → 发票报关字段（产品信息总表）
- extra_data → JSON 冗余列，存总表未映射字段

数据库结构变更规则（禁止 drop_all / 删库重建）：
  backend/docs/数据库安全更新指南.txt
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fba_tool.app_paths import master_db_path as _master_db_file
from fba_tool.sku_keys import SkuCaseConflict, case_conflicts, pick_candidate, sku_key, sku_text

DB_FILENAME = "fba_master.db"
SQLITE_TIMEOUT_SEC = 30

UNIT_FIELDS = ("unit_length", "unit_width", "unit_height", "unit_weight")
CARTON_FIELDS = ("carton_length", "carton_width", "carton_height", "carton_weight")
CODE_FIELDS = ("asin", "fnsku")
INVOICE_TEXT_FIELDS = ("chinese_name", "english_name", "hs_code", "material", "purpose", "brand")
OPS_TEXT_FIELDS = ("model_name",)
MASTER_TEXT_FIELDS = INVOICE_TEXT_FIELDS + OPS_TEXT_FIELDS
INVOICE_FLOAT_FIELDS = ("declared_value", "qty_per_box")
# 领星 Listing 身份字段：可覆盖；箱规/报关/单品尺寸禁止由领星覆盖（同步时不写入这些列）。
LINGXING_TEXT_FIELDS = ("parent_asin", "listing_status", "fulfillment_channel", "data_source", "lingxing_synced_at")
LINGXING_INT_FIELDS = ("sid",)
LOCAL_GUARD_FIELDS = UNIT_FIELDS + CARTON_FIELDS + (
    "qty_per_box",
    "hs_code",
    "declared_value",
    "material",
    "purpose",
    "chinese_name",
)
PATCHABLE_FIELDS: Set[str] = set(
    CODE_FIELDS
    + UNIT_FIELDS
    + CARTON_FIELDS
    + MASTER_TEXT_FIELDS
    + INVOICE_FLOAT_FIELDS
    + ("extra_data", "parent_asin", "listing_status", "fulfillment_channel")
)


def master_db_path() -> Path:
    path = _master_db_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class _BatchConn:
    """S9-final N5：批量写入共用的连接。commit / close / with 退出都不真正提交，由 batch_transaction 统一提交或回滚。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def commit(self) -> None:  # 推迟到 batch_transaction 结束
        return None

    def close(self) -> None:
        return None

    def __enter__(self) -> "_BatchConn":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


_BATCH = threading.local()


@contextmanager
def batch_transaction():
    """S9-final N5：一个事务里写一批（导入确认用）。块内所有 _connect() 共用一个连接；
    正常结束一次提交，任何异常整体回滚、再抛出。可嵌套（内层直接复用外层）。"""
    if getattr(_BATCH, "conn", None) is not None:
        yield _BATCH.conn
        return
    real = _open_connection()
    _BATCH.conn = _BatchConn(real)
    try:
        yield _BATCH.conn
        real.commit()
    except BaseException:
        real.rollback()
        raise
    finally:
        _BATCH.conn = None
        real.close()


def _connect() -> Any:
    batch = getattr(_BATCH, "conn", None)
    if batch is not None:
        return batch
    return _open_connection()


def _open_connection() -> sqlite3.Connection:
    path = master_db_path()
    conn = sqlite3.connect(path, check_same_thread=False, timeout=SQLITE_TIMEOUT_SEC)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    conn.create_function("sku_key", 1, sku_key)  # S9-step3：SKU 匹配统一用 sku_key（NFKC + 去首尾空白 + casefold）
    return conn


def _sku_candidates(conn: sqlite3.Connection, sku: Any) -> List[str]:
    """S9-step3：按规范键找库里的 SKU（原始写法）。先走主键精确查，没有再按规范键全表比对。"""
    text = sku_text(sku)
    if not text:
        return []
    key = sku_key(text)
    rows = conn.execute("SELECT sku FROM product_master WHERE sku_key(sku) = ?", (key,)).fetchall()
    return [str(r[0]) for r in rows]


def resolve_stored_sku(sku: Any, conn: Optional[sqlite3.Connection] = None) -> Optional[str]:
    """S9-step3：把输入的 SKU 匹配到库里原样存储的那条：原样相同优先；规范键只命中一条就用它；
    命中多条只差大小写/全角半角的、又没有原样相同的 → SkuCaseConflict（不静默任选）；没有返回 None。"""
    text = sku_text(sku)
    if not text:
        return None
    if conn is None:
        with _connect() as c:
            return resolve_stored_sku(text, c)
    row = conn.execute("SELECT sku FROM product_master WHERE sku = ?", (text,)).fetchone()
    if row:
        return str(row[0])
    return pick_candidate(text, _sku_candidates(conn, text))


def list_sku_case_conflicts() -> List[List[str]]:
    """S9-step3：库里只差大小写/全角半角的 SKU 组（旧数据可能有）。不自动合并，只用于提示。"""
    with _connect() as conn:
        rows = conn.execute("SELECT sku FROM product_master").fetchall()
    return sorted(case_conflicts(str(r[0]) for r in rows).values())


def sku_conflicts_for(skus: List[Any]) -> Dict[str, List[str]]:
    """S9-step3：这些 SKU 里匹配有冲突的（多个只差大小写的候选且没有原样相同的）→ {输入 SKU: 候选}。"""
    out: Dict[str, List[str]] = {}
    with _connect() as conn:
        for s in skus:
            text = sku_text(s)
            if not text or text in out:
                continue
            try:
                resolve_stored_sku(text, conn)
            except SkuCaseConflict as exc:
                out[text] = exc.candidates
    return out


def _table_columns(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("PRAGMA table_info(product_master)").fetchall()
    return {str(r[1]) for r in rows}


def _migrate_schema(conn: sqlite3.Connection) -> None:
    cols = _table_columns(conn)
    if not cols:
        return

    legacy_unit = [
        "unit_length",
        "unit_width",
        "unit_height",
        "unit_weight",
        "carton_length",
        "carton_width",
        "carton_height",
        "carton_weight",
    ]
    for name in legacy_unit:
        if name not in cols:
            conn.execute(f"ALTER TABLE product_master ADD COLUMN {name} REAL")

    invoice_text = [
        "chinese_name",
        "model_name",
        "english_name",
        "hs_code",
        "material",
        "purpose",
        "brand",
        "extra_data",
    ]
    for name in invoice_text:
        if name not in cols:
            conn.execute(f"ALTER TABLE product_master ADD COLUMN {name} TEXT")

    if "declared_value" not in cols:
        conn.execute("ALTER TABLE product_master ADD COLUMN declared_value REAL")

    if "qty_per_box" not in cols:
        conn.execute("ALTER TABLE product_master ADD COLUMN qty_per_box REAL")

    lingxing_text = [
        "parent_asin",
        "listing_status",
        "fulfillment_channel",
        "lingxing_synced_at",
        "data_source",
    ]
    for name in lingxing_text:
        if name not in cols:
            conn.execute(f"ALTER TABLE product_master ADD COLUMN {name} TEXT")
    if "sid" not in cols:
        conn.execute("ALTER TABLE product_master ADD COLUMN sid INTEGER")

    cols = _table_columns(conn)
    if "length" in cols and "unit_length" in cols:
        conn.execute(
            """
            UPDATE product_master
            SET unit_length = COALESCE(unit_length, length),
                unit_width = COALESCE(unit_width, width),
                unit_height = COALESCE(unit_height, height),
                unit_weight = COALESCE(unit_weight, weight)
            WHERE length IS NOT NULL OR width IS NOT NULL OR height IS NOT NULL OR weight IS NOT NULL
            """
        )


def init_master_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS product_master (
                sku TEXT PRIMARY KEY,
                asin TEXT,
                fnsku TEXT,
                unit_length REAL,
                unit_width REAL,
                unit_height REAL,
                unit_weight REAL,
                carton_length REAL,
                carton_width REAL,
                carton_height REAL,
                carton_weight REAL,
                chinese_name TEXT,
                model_name TEXT,
                english_name TEXT,
                hs_code TEXT,
                material TEXT,
                purpose TEXT,
                brand TEXT,
                declared_value REAL,
                qty_per_box REAL,
                extra_data TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        _migrate_schema(conn)
        from fba_tool.product_fields import migrate as _migrate_s2

        _migrate_s2(conn)
        _ensure_lingxing_tables(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_product_master_asin ON product_master(asin)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_product_master_fnsku ON product_master(fnsku)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_product_master_sid ON product_master(sid)")
        conn.commit()


def _ensure_lingxing_tables(conn: sqlite3.Connection) -> None:
    """快照/同步表：只 CREATE IF NOT EXISTS，禁止 DROP。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lingxing_shop (
            sid INTEGER PRIMARY KEY,
            name TEXT,
            country TEXT,
            country_code TEXT,
            seller_id TEXT,
            currency TEXT,
            platform_name TEXT,
            status INTEGER,
            extra_json TEXT,
            synced_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lingxing_fba_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL,
            asin TEXT,
            fnsku TEXT,
            sid INTEGER,
            seller_name TEXT,
            fulfillable REAL,
            reserved REAL,
            inbound_shipped REAL,
            inbound_working REAL,
            inbound_receiving REAL,
            unfulfillable REAL,
            age_0_30 REAL,
            age_31_60 REAL,
            age_61_90 REAL,
            age_91_180 REAL,
            total_cost REAL,
            extra_json TEXT,
            synced_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lingxing_fba_stock_sku ON lingxing_fba_stock(sku)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lingxing_fba_stock_asin ON lingxing_fba_stock(asin)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lingxing_replenish (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT,
            asin TEXT,
            sid INTEGER,
            title TEXT,
            days_fba REAL,
            qty_purchase REAL,
            qty_local_to_fba REAL,
            sales_30 REAL,
            fulfillable REAL,
            out_stock_date TEXT,
            extra_json TEXT,
            synced_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lingxing_replenish_sku ON lingxing_replenish(sku)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lingxing_asin_perf (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asin TEXT,
            title TEXT,
            amount REAL,
            volume REAL,
            gross_profit REAL,
            spend REAL,
            acos REAL,
            return_rate REAL,
            sessions REAL,
            extra_json TEXT,
            period_start TEXT,
            period_end TEXT,
            synced_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lingxing_asin_perf_asin ON lingxing_asin_perf(asin)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lingxing_sync_run (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT,
            steps_json TEXT,
            counts_json TEXT,
            error TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lingxing_sync_diff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            kind TEXT,
            sku TEXT,
            message TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lingxing_sync_diff_run ON lingxing_sync_diff(run_id)"
    )
    # S5：定时同步——记录触发方式（manual / scheduled / retry）和第几次尝试
    run_cols = {r[1] for r in conn.execute("PRAGMA table_info(lingxing_sync_run)")}
    if "trigger" not in run_cols:
        conn.execute("ALTER TABLE lingxing_sync_run ADD COLUMN trigger TEXT DEFAULT 'manual'")
    if "attempt" not in run_cols:
        conn.execute("ALTER TABLE lingxing_sync_run ADD COLUMN attempt INTEGER DEFAULT 1")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lingxing_sync_preview_sku (
            run_id INTEGER NOT NULL,
            sku TEXT NOT NULL,
            is_new INTEGER NOT NULL DEFAULT 0,
            group_kind TEXT NOT NULL,
            mismatch_skus TEXT,
            remote_json TEXT NOT NULL,
            PRIMARY KEY (run_id, sku)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lingxing_sync_preview_field (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            sku TEXT NOT NULL,
            field TEXT NOT NULL,
            local_value TEXT,
            remote_value TEXT,
            default_checked INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lingxing_preview_field_run ON lingxing_sync_preview_field(run_id, sku)"
    )


def upsert_product(record: Dict[str, Any], overwrite: bool = False) -> None:
    sku = str(record.get("sku") or "").strip()
    if not sku:
        return
    # S9-step3：先按规范键匹配到库里已有的那条（保留库里原始写法），不再因为只差大小写就新建一行；
    # 多个候选又没有原样相同的 → SkuCaseConflict，不写。
    sku = resolve_stored_sku(sku) or sku
    existing = get_product_by_sku(sku)
    merged: Dict[str, Any] = {"sku": sku}
    for field in CODE_FIELDS + MASTER_TEXT_FIELDS:
        if overwrite and field in record:
            merged[field] = _opt_str(record[field])
        else:
            merged[field] = _pick_merge(record.get(field), existing.get(field) if existing else None)
    for field in UNIT_FIELDS + CARTON_FIELDS + INVOICE_FLOAT_FIELDS:
        if overwrite and field in record:
            v = _opt_float(record[field])
            merged[field] = v if v is not None and v > 0 else None
        else:
            merged[field] = _pick_merge_float(record.get(field), existing.get(field) if existing else None)

    if overwrite and "extra_data" in record:
        extra_new = record.get("extra_data")
        if extra_new in (None, "", {}):
            merged["extra_data"] = None
        elif isinstance(extra_new, dict):
            merged["extra_data"] = json.dumps(extra_new, ensure_ascii=False)
        else:
            merged["extra_data"] = str(extra_new).strip()
    else:
        extra_new = record.get("extra_data")
        extra_old = existing.get("extra_data") if existing else None
        merged["extra_data"] = _merge_extra_data(extra_new, extra_old)

    for field in ("parent_asin", "listing_status", "fulfillment_channel"):
        if overwrite and field in record:
            merged[field] = _opt_str(record[field])
        else:
            merged[field] = _pick_merge(record.get(field), existing.get(field) if existing else None)

    if overwrite and "sid" in record:
        merged["sid"] = _opt_int(record.get("sid"))
    else:
        merged["sid"] = _pick_merge_int(record.get("sid"), existing.get("sid") if existing else None)

    incoming_source = _opt_str(record.get("data_source"))
    old_source = _opt_str(existing.get("data_source")) if existing else None
    if incoming_source:
        if existing and _has_local_guard_values(existing) and incoming_source == "lingxing":
            merged["data_source"] = "mixed"
        else:
            merged["data_source"] = incoming_source
    else:
        merged["data_source"] = old_source

    incoming_synced = _opt_str(record.get("lingxing_synced_at"))
    merged["lingxing_synced_at"] = incoming_synced or (
        _opt_str(existing.get("lingxing_synced_at")) if existing else None
    )

    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO product_master (
                sku, asin, fnsku,
                unit_length, unit_width, unit_height, unit_weight,
                carton_length, carton_width, carton_height, carton_weight,
                chinese_name, model_name, english_name, hs_code, material, purpose, brand,
                declared_value, qty_per_box, extra_data, updated_at,
                parent_asin, sid, listing_status, fulfillment_channel,
                lingxing_synced_at, data_source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sku) DO UPDATE SET
                asin = excluded.asin,
                fnsku = excluded.fnsku,
                unit_length = excluded.unit_length,
                unit_width = excluded.unit_width,
                unit_height = excluded.unit_height,
                unit_weight = excluded.unit_weight,
                carton_length = excluded.carton_length,
                carton_width = excluded.carton_width,
                carton_height = excluded.carton_height,
                carton_weight = excluded.carton_weight,
                chinese_name = excluded.chinese_name,
                model_name = excluded.model_name,
                english_name = excluded.english_name,
                hs_code = excluded.hs_code,
                material = excluded.material,
                purpose = excluded.purpose,
                brand = excluded.brand,
                declared_value = excluded.declared_value,
                qty_per_box = excluded.qty_per_box,
                extra_data = excluded.extra_data,
                updated_at = excluded.updated_at,
                parent_asin = excluded.parent_asin,
                sid = excluded.sid,
                listing_status = excluded.listing_status,
                fulfillment_channel = excluded.fulfillment_channel,
                lingxing_synced_at = excluded.lingxing_synced_at,
                data_source = excluded.data_source
            """,
            (
                sku,
                merged["asin"],
                merged["fnsku"],
                merged["unit_length"],
                merged["unit_width"],
                merged["unit_height"],
                merged["unit_weight"],
                merged["carton_length"],
                merged["carton_width"],
                merged["carton_height"],
                merged["carton_weight"],
                merged["chinese_name"],
                merged["model_name"],
                merged["english_name"],
                merged["hs_code"],
                merged["material"],
                merged["purpose"],
                merged["brand"],
                merged["declared_value"],
                merged["qty_per_box"],
                merged["extra_data"],
                now,
                merged["parent_asin"],
                merged["sid"],
                merged["listing_status"],
                merged["fulfillment_channel"],
                merged["lingxing_synced_at"],
                merged["data_source"],
            ),
        )
        conn.commit()


def patch_product_field(sku: str, field: str, value: Any) -> Dict[str, Any]:
    key = str(sku or "").strip()
    field_key = str(field or "").strip()
    if not key:
        raise ValueError("SKU 不能为空")
    from fba_tool.product_fields import OWN_FIELDS, SOURCE_MANUAL, WRITABLE_FIELDS, set_product_fields

    # S8 D5：HS 编码校验格式；数字字段填了非数字要报错，不能悄悄忽略
    if field_key in ("hs_code", "dest_hs_code"):
        from fba_tool.hs_code import normalize_hs_code

        value = normalize_hs_code(value)
    if (field_key in INVOICE_FLOAT_FIELDS or field_key in UNIT_FIELDS + CARTON_FIELDS
            or field_key in ("listing_price", "carton_gross_weight")) and str(value if value is not None else "").strip() != "":
        if _opt_float(value) is None:
            raise ValueError(f"{field_key} 必须是数字，收到「{value}」，未保存")
    if field_key in OWN_FIELDS:
        set_product_fields(key, {field_key: value}, SOURCE_MANUAL)
        rec = get_product_by_sku(key)
        if not rec:
            raise ValueError(f"更新失败：{key}")
        return rec
    if field_key not in PATCHABLE_FIELDS:
        raise ValueError(f"不允许更新的字段：{field_key}")

    existing = get_product_by_sku(key)
    if not existing:
        existing = {"sku": key}

    if field_key in INVOICE_FLOAT_FIELDS or field_key in UNIT_FIELDS + CARTON_FIELDS:
        existing[field_key] = _opt_float(value)
    elif field_key == "extra_data":
        if isinstance(value, dict):
            existing[field_key] = json.dumps(value, ensure_ascii=False)
        else:
            existing[field_key] = str(value or "").strip() or None
    else:
        existing[field_key] = _opt_str(value)

    upsert_product(existing)
    # 手填过的字段记为 manual，之后领星同步不覆盖（D-2026-10-16-03：网页/本地改的任何字段都锁定；申报价例外见 NEVER_LOCKED_FOR_LINGXING）
    if field_key in WRITABLE_FIELDS and existing.get(field_key) not in (None, ""):
        set_product_fields(key, {field_key: existing[field_key]}, SOURCE_MANUAL)
    elif field_key != "extra_data" and existing.get(field_key) not in (None, ""):
        from fba_tool.product_fields import mark_field_sources

        mark_field_sources(key, [field_key], SOURCE_MANUAL)
    rec = get_product_by_sku(key)
    if not rec:
        raise ValueError(f"更新失败：{key}")
    return rec


def upsert_products(records: List[Dict[str, Any]], overwrite: bool = False) -> int:
    count = 0
    for rec in records:
        if str(rec.get("sku") or "").strip():
            upsert_product(rec, overwrite=overwrite)
            count += 1
    return count


def delete_product_by_sku(sku: str) -> bool:
    """物理删除 SKU 行。"""
    key = str(sku or "").strip()
    if not key:
        return False
    with _connect() as conn:
        stored = resolve_stored_sku(key, conn)  # S9-step3：只删匹配到的那一条；冲突时报错，不一次删掉所有大小写变体
        if stored is None:
            return False
        cur = conn.execute(
            "DELETE FROM product_master WHERE sku = ?",
            (stored,),
        )
        conn.commit()
        return cur.rowcount > 0


def _get_row(conn: sqlite3.Connection, sku: Any) -> Optional[sqlite3.Row]:
    """S9-step3：按统一规则匹配一条；冲突（多个只差大小写、没有原样相同）时记日志并返回 None，不任选。"""
    try:
        stored = resolve_stored_sku(sku, conn)
    except SkuCaseConflict as exc:
        import logging

        logging.getLogger(__name__).warning("%s", exc)
        return None
    if stored is None:
        return None
    return conn.execute("SELECT * FROM product_master WHERE sku = ?", (stored,)).fetchone()


def get_product_by_sku(sku: str) -> Optional[Dict[str, Any]]:
    key = str(sku or "").strip()
    if not key:
        return None
    with _connect() as conn:
        row = _get_row(conn, key)
    return _row_to_dict(row) if row else None


def list_products(limit: int = 5000, customs_status: str = "") -> List[Dict[str, Any]]:
    """customs_status="missing" 只返回“缺报关配置”的产品。每行带 customs_config_missing / customs_config_status。"""
    from fba_tool.hs_config import MISSING_LABEL, all_templates_map, customs_config_missing

    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM product_master ORDER BY sku COLLATE NOCASE LIMIT ?",
            (int(limit),),
        ).fetchall()
    tpls = all_templates_map()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = _row_to_dict(r)
        miss = customs_config_missing(d, tpls)
        d["customs_config_missing"] = miss
        d["customs_config_status"] = MISSING_LABEL if miss else ""
        if customs_status == "missing" and not miss:
            continue
        out.append(d)
    return out


def get_products_by_skus(skus: List[str]) -> Dict[str, Dict[str, Any]]:
    keys = [str(s).strip() for s in skus if str(s).strip()]
    if not keys:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    with _connect() as conn:
        for key in keys:
            row = _get_row(conn, key)
            if row:
                rec = _row_to_dict(row)
                # S9-step3：以“输入的 SKU”为键（调用方用输入 SKU 取值），同时保留库里原始写法作键（兼容旧调用）
                out[key] = rec
                out.setdefault(str(rec["sku"]).strip(), rec)
    return out


def fnsku_mapping() -> Dict[str, str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT sku, fnsku FROM product_master WHERE fnsku IS NOT NULL AND TRIM(fnsku) != ''"
        ).fetchall()
    return {str(r["sku"]).strip(): str(r["fnsku"]).strip() for r in rows}


def amazon_sku_metadata() -> Dict[str, dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM product_master").fetchall()
    meta: Dict[str, dict] = {}
    for row in rows:
        rec = _row_to_dict(row)
        sku = str(rec.get("sku") or "").strip()
        if not sku:
            continue
        meta[sku] = {
            "product_name": rec.get("english_name") or rec.get("chinese_name") or sku,
            "id": rec.get("asin") or "",
            "asin": rec.get("asin") or "",
            "fnsku": rec.get("fnsku") or "",
            "length_cm": rec.get("unit_length"),
            "width_cm": rec.get("unit_width"),
            "height_cm": rec.get("unit_height"),
            "weight_kg": rec.get("unit_weight"),
        }
    return meta


def lookup_model_name(sku: str) -> str:
    """中文名称(型号)：工人实操单、发货表展示用。"""
    rec = get_product_by_sku(sku)
    if not rec:
        return ""
    return str(rec.get("model_name") or "").strip()


def lookup_customs_name(sku: str) -> str:
    """商品报关名称：发票/报关用。"""
    rec = get_product_by_sku(sku)
    if not rec:
        return ""
    return str(rec.get("chinese_name") or "").strip()


def lookup_by_fnsku(fnsku: str) -> Optional[Dict[str, Any]]:
    key = str(fnsku or "").strip()
    if not key:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM product_master WHERE fnsku = ? COLLATE NOCASE",
            (key,),
        ).fetchone()
    return _row_to_dict(row) if row else None


_ROW_SKIP = {"field_source_json", "length", "width", "height", "weight"}


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    keys = row.keys()
    unit_length = _col_float(row, "unit_length")
    unit_width = _col_float(row, "unit_width")
    unit_height = _col_float(row, "unit_height")
    unit_weight = _col_float(row, "unit_weight")

    if unit_length is None and "length" in keys:
        unit_length = _col_float(row, "length")
        unit_width = _col_float(row, "width")
        unit_height = _col_float(row, "height")
        unit_weight = _col_float(row, "weight")

    out = {
        "sku": row["sku"],
        "asin": row["asin"] or "",
        "fnsku": row["fnsku"] or "",
        "unit_length": unit_length,
        "unit_width": unit_width,
        "unit_height": unit_height,
        "unit_weight": unit_weight,
        "carton_length": _col_float(row, "carton_length") if "carton_length" in keys else None,
        "carton_width": _col_float(row, "carton_width") if "carton_width" in keys else None,
        "carton_height": _col_float(row, "carton_height") if "carton_height" in keys else None,
        "carton_weight": _col_float(row, "carton_weight") if "carton_weight" in keys else None,
        "chinese_name": _col_str(row, "chinese_name"),
        "model_name": _col_str(row, "model_name") if "model_name" in keys else "",
        "english_name": _col_str(row, "english_name"),
        "hs_code": _col_str(row, "hs_code"),
        "material": _col_str(row, "material"),
        "purpose": _col_str(row, "purpose"),
        "brand": _col_str(row, "brand"),
        "declared_value": _col_float(row, "declared_value"),
        "qty_per_box": _col_float(row, "qty_per_box") if "qty_per_box" in keys else None,
        "extra_data": _col_str(row, "extra_data"),
        "updated_at": row["updated_at"],
        "parent_asin": _col_str(row, "parent_asin") if "parent_asin" in keys else "",
        "sid": _col_int(row, "sid") if "sid" in keys else None,
        "listing_status": _col_str(row, "listing_status") if "listing_status" in keys else "",
        "fulfillment_channel": _col_str(row, "fulfillment_channel") if "fulfillment_channel" in keys else "",
        "lingxing_synced_at": _col_str(row, "lingxing_synced_at") if "lingxing_synced_at" in keys else "",
        "data_source": _col_str(row, "data_source") if "data_source" in keys else "",
        "listing_price": _col_float(row, "listing_price") if "listing_price" in keys else None,
        "listing_price_currency": _col_str(row, "listing_price_currency") if "listing_price_currency" in keys else "",
        "listing_price_at": _col_str(row, "listing_price_at") if "listing_price_at" in keys else "",
        "declare_unit": _col_str(row, "declare_unit") if "declare_unit" in keys else "",
        "local_name": _col_str(row, "local_name") if "local_name" in keys else "",
        "listing_price_basis": _col_str(row, "listing_price_basis") if "listing_price_basis" in keys else "",
        "category": _col_str(row, "category") if "category" in keys else "",
        "carton_gross_weight": _col_float(row, "carton_gross_weight") if "carton_gross_weight" in keys else None,
        "field_sources": _json_dict(row["field_source_json"]) if "field_source_json" in keys else {},
        # S8-fix1 N1：D-12 正常价相关列（以前漏读，导致促销按正常价申报在真实链路上不生效）
        "regular_price": _col_float(row, "regular_price") if "regular_price" in keys else None,
        "regular_price_at": _col_str(row, "regular_price_at") if "regular_price_at" in keys else "",
        "last_nonpromo_price": _col_float(row, "last_nonpromo_price") if "last_nonpromo_price" in keys else None,
        "last_nonpromo_at": _col_str(row, "last_nonpromo_at") if "last_nonpromo_at" in keys else "",
    }
    # S8-fix1：以后新增的列（product_fields.ensure 加的 ALTER TABLE 列）不再被悄悄丢掉——原样带出
    for k in keys:
        if k not in out and k not in _ROW_SKIP:
            out[k] = row[k]
    return out


def _json_dict(text: Any) -> Dict[str, Any]:
    if not text:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _col_str(row: sqlite3.Row, name: str) -> str:
    if name not in row.keys():
        return ""
    return str(row[name] or "").strip()


def _col_float(row: sqlite3.Row, name: str) -> Optional[float]:
    if name not in row.keys():
        return None
    return _opt_float(row[name])


def _col_int(row: sqlite3.Row, name: str) -> Optional[int]:
    if name not in row.keys():
        return None
    return _opt_int(row[name])


def _opt_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _opt_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _opt_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _pick_merge_int(new_val: Any, old_val: Any) -> Optional[int]:
    val = _opt_int(new_val)
    if val is not None:
        return val
    return _opt_int(old_val)


def _has_local_guard_values(existing: Dict[str, Any]) -> bool:
    for field in LOCAL_GUARD_FIELDS:
        val = existing.get(field)
        if val is None or val == "":
            continue
        if isinstance(val, (int, float)) and float(val) > 0:
            return True
        if isinstance(val, str) and val.strip():
            return True
    return False


def _pick_merge(new_val: Any, old_val: Any) -> Optional[str]:
    text = _opt_str(new_val)
    if text:
        return text
    return _opt_str(old_val)


def _pick_merge_float(new_val: Any, old_val: Any) -> Optional[float]:
    val = _opt_float(new_val)
    if val is not None and val > 0:
        return val
    old = _opt_float(old_val)
    return old if old and old > 0 else None


def _merge_extra_data(new_val: Any, old_val: Any) -> Optional[str]:
    if new_val in (None, "", {}):
        return _opt_str(old_val)
    if isinstance(new_val, dict):
        new_text = json.dumps(new_val, ensure_ascii=False)
    else:
        new_text = str(new_val).strip()
    if not new_text:
        return _opt_str(old_val)
    old_text = _opt_str(old_val)
    if not old_text:
        return new_text
    try:
        old_obj = json.loads(old_text)
        new_obj = json.loads(new_text) if isinstance(new_val, str) else new_val
        if isinstance(old_obj, dict) and isinstance(new_obj, dict):
            merged = {**old_obj, **new_obj}
            return json.dumps(merged, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        pass
    return new_text


def list_skus_for_asin(asin: str) -> List[str]:
    key = str(asin or "").strip()
    if not key:
        return []
    with _connect() as conn:
        rows = conn.execute(
            "SELECT sku FROM product_master WHERE asin = ? COLLATE NOCASE",
            (key,),
        ).fetchall()
    return [str(r["sku"]).strip() for r in rows if str(r["sku"] or "").strip()]


def replace_lingxing_shops(rows: List[Dict[str, Any]]) -> int:
    synced_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute("DELETE FROM lingxing_shop")
        for rec in rows:
            sid = _opt_int(rec.get("sid"))
            if sid is None:
                continue
            extra = rec.get("extra_json")
            extra_text = extra if isinstance(extra, str) else (
                json.dumps(extra, ensure_ascii=False) if extra else None
            )
            conn.execute(
                """
                INSERT INTO lingxing_shop (
                    sid, name, country, country_code, seller_id, currency,
                    platform_name, status, extra_json, synced_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sid) DO UPDATE SET
                    name = excluded.name,
                    country = excluded.country,
                    country_code = excluded.country_code,
                    seller_id = excluded.seller_id,
                    currency = excluded.currency,
                    platform_name = excluded.platform_name,
                    status = excluded.status,
                    extra_json = excluded.extra_json,
                    synced_at = excluded.synced_at
                """,
                (
                    sid,
                    _opt_str(rec.get("name")),
                    _opt_str(rec.get("country")),
                    _opt_str(rec.get("country_code")),
                    _opt_str(rec.get("seller_id")),
                    _opt_str(rec.get("currency")),
                    _opt_str(rec.get("platform_name")),
                    _opt_int(rec.get("status")),
                    extra_text,
                    synced_at,
                ),
            )
        conn.commit()
    return len(rows)


def replace_lingxing_fba_stock(rows: List[Dict[str, Any]], synced_at: str) -> int:
    with _connect() as conn:
        conn.execute("DELETE FROM lingxing_fba_stock")
        conn.executemany(
            """
            INSERT INTO lingxing_fba_stock (
                sku, asin, fnsku, sid, seller_name,
                fulfillable, reserved, inbound_shipped, inbound_working, inbound_receiving,
                unfulfillable, age_0_30, age_31_60, age_61_90, age_91_180,
                total_cost, extra_json, synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    rec.get("sku"),
                    rec.get("asin"),
                    rec.get("fnsku"),
                    rec.get("sid"),
                    rec.get("seller_name"),
                    rec.get("fulfillable"),
                    rec.get("reserved"),
                    rec.get("inbound_shipped"),
                    rec.get("inbound_working"),
                    rec.get("inbound_receiving"),
                    rec.get("unfulfillable"),
                    rec.get("age_0_30"),
                    rec.get("age_31_60"),
                    rec.get("age_61_90"),
                    rec.get("age_91_180"),
                    rec.get("total_cost"),
                    rec.get("extra_json"),
                    synced_at,
                )
                for rec in rows
            ],
        )
        conn.commit()
    return len(rows)


def replace_lingxing_replenish(rows: List[Dict[str, Any]], synced_at: str) -> int:
    with _connect() as conn:
        conn.execute("DELETE FROM lingxing_replenish")
        conn.executemany(
            """
            INSERT INTO lingxing_replenish (
                sku, asin, sid, title, days_fba, qty_purchase, qty_local_to_fba,
                sales_30, fulfillable, out_stock_date, extra_json, synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    rec.get("sku"),
                    rec.get("asin"),
                    rec.get("sid"),
                    rec.get("title"),
                    rec.get("days_fba"),
                    rec.get("qty_purchase"),
                    rec.get("qty_local_to_fba"),
                    rec.get("sales_30"),
                    rec.get("fulfillable"),
                    rec.get("out_stock_date"),
                    rec.get("extra_json"),
                    synced_at,
                )
                for rec in rows
            ],
        )
        conn.commit()
    return len(rows)


def replace_lingxing_asin_perf(rows: List[Dict[str, Any]], synced_at: str) -> int:
    with _connect() as conn:
        conn.execute("DELETE FROM lingxing_asin_perf")
        conn.executemany(
            """
            INSERT INTO lingxing_asin_perf (
                asin, title, amount, volume, gross_profit, spend, acos,
                return_rate, sessions, extra_json, period_start, period_end, synced_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    rec.get("asin"),
                    rec.get("title"),
                    rec.get("amount"),
                    rec.get("volume"),
                    rec.get("gross_profit"),
                    rec.get("spend"),
                    rec.get("acos"),
                    rec.get("return_rate"),
                    rec.get("sessions"),
                    rec.get("extra_json"),
                    rec.get("period_start"),
                    rec.get("period_end"),
                    synced_at,
                )
                for rec in rows
            ],
        )
        conn.commit()
    return len(rows)


def create_lingxing_sync_run() -> int:
    started = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO lingxing_sync_run (started_at, status) VALUES (?, ?)",
            (started, "running"),
        )
        conn.commit()
        return int(cur.lastrowid)


def finish_lingxing_sync_run(
    run_id: int,
    status: str,
    steps: Any,
    counts: Any,
    error: Optional[str] = None,
) -> None:
    finished = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE lingxing_sync_run
            SET finished_at = ?, status = ?, steps_json = ?, counts_json = ?, error = ?
            WHERE id = ?
            """,
            (
                finished,
                status,
                json.dumps(steps, ensure_ascii=False),
                json.dumps(counts, ensure_ascii=False),
                error,
                run_id,
            ),
        )
        conn.commit()


def add_lingxing_sync_diff(run_id: int, kind: str, sku: str, message: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO lingxing_sync_diff (run_id, kind, sku, message, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, kind, sku, message, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def list_lingxing_sync_diffs(run_id: int) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT kind, sku, message FROM lingxing_sync_diff WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
    return [{"kind": r["kind"], "sku": r["sku"], "message": r["message"]} for r in rows]


def get_latest_lingxing_sync_run() -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM lingxing_sync_run ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return {k: row[k] for k in row.keys()}


def list_lingxing_shops() -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM lingxing_shop ORDER BY sid").fetchall()
    return [{k: row[k] for k in row.keys()} for row in rows]


def list_lingxing_stock_alerts(days_threshold: float = 14.0) -> List[Dict[str, Any]]:
    """可售天数过低或建议本地发 FBA 的 SKU。不以「库存=0 的全部 Listing」当断货名单。"""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT sku, asin, sid, title, days_fba, fulfillable, qty_local_to_fba, out_stock_date
            FROM lingxing_replenish
            WHERE (days_fba IS NOT NULL AND days_fba <= ?)
               OR (qty_local_to_fba IS NOT NULL AND qty_local_to_fba > 0)
            ORDER BY COALESCE(days_fba, 9999) ASC, sku
            """,
            (float(days_threshold),),
        ).fetchall()
    items = []
    for r in rows:
        days = r["days_fba"]
        qty = r["qty_local_to_fba"]
        if days is not None and float(days) <= 0:
            message = "FBA 可售天数已耗尽（断货）"
        elif days is not None and float(days) <= days_threshold:
            message = f"可售天数约 {days} 天"
        elif qty is not None and float(qty) > 0:
            message = f"建议发往 FBA {qty} 件"
        else:
            message = "需要关注补货"
        items.append(
            {
                "sku": r["sku"] or "",
                "asin": r["asin"] or "",
                "sid": r["sid"],
                "title": r["title"] or "",
                "days_fba": days,
                "fulfillable": r["fulfillable"],
                "qty_local_to_fba": qty,
                "out_stock_date": r["out_stock_date"] or "",
                "message": message,
            }
        )
    return items


def invoice_hints_from_master(master: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """运行时发票/报关提示：只读 SQLite，不含产品信息表.csv。"""
    if not master:
        return {}
    hints: Dict[str, Any] = {}
    if master.get("chinese_name"):
        hints["中文品名"] = master["chinese_name"]
    if master.get("english_name"):
        hints["英文品名"] = master["english_name"]
    if master.get("hs_code"):
        hints["海关编码"] = master["hs_code"]
    if master.get("brand"):
        hints["品牌"] = master["brand"]
    if master.get("material"):
        hints["材料"] = master["material"]
    if master.get("purpose"):
        hints["用途"] = master["purpose"]
    from fba_tool.product_fields import resolve_declared_price

    price, price_source = resolve_declared_price(master)
    if price is not None:
        hints["单个货值"] = price
        hints["申报价来源"] = price_source
    from fba_tool.product_fields import promo_info

    _promo = promo_info(master)
    if _promo:
        hints["促销售价"] = _promo["listing_price"]  # D-12：促销期按正常价申报，导出时提示
    dv = master.get("declared_value")
    if price_source.startswith("lingxing") and dv not in (None, ""):
        hints["历史申报价"] = dv
        if (master.get("field_sources") or {}).get("declared_value") == "manual":
            hints["手填申报价"] = dv  # 手填价没被采用，导出时提示（docs/用户决策记录.md D-2026-10-16-01）
    if master.get("declare_unit"):
        hints["declare_unit"] = master["declare_unit"]
    if master.get("category"):
        hints["品类"] = master["category"]
    if master.get("model_name"):
        hints["型号"] = master["model_name"]
    if master.get("asin"):
        hints["ASIN"] = master["asin"]
    if master.get("fnsku"):
        hints["FNSKU"] = master["fnsku"]
    return hints


LINGXING_SUCCESS_STATUSES = ("auto_applied", "auto_applied_partial", "preview_pending", "partial", "confirmed")


def get_last_lingxing_sync_success_at() -> Optional[str]:
    """上次成功同步（拉取成功，含手动拉取）的完成时间，存在 lingxing_sync_run.finished_at。"""
    q = ",".join("?" * len(LINGXING_SUCCESS_STATUSES))
    with _connect() as conn:
        row = conn.execute(f"SELECT MAX(finished_at) FROM lingxing_sync_run WHERE status IN ({q}) AND finished_at IS NOT NULL",
                           LINGXING_SUCCESS_STATUSES).fetchone()
    return row[0] if row and row[0] else None


def tag_lingxing_sync_run(run_id: int, trigger: str, attempt: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE lingxing_sync_run SET trigger = ?, attempt = ? WHERE id = ?", (trigger, int(attempt), int(run_id)))
        conn.commit()


def list_lingxing_sync_runs(limit: int = 50) -> List[Dict[str, Any]]:
    """同步记录（新→旧），带各类差异条数，供界面“同步记录”表。"""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM lingxing_sync_run ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        out = []
        for r in rows:
            d = {k: r[k] for k in r.keys()}
            d["diff_counts"] = {k: n for k, n in conn.execute(
                "SELECT kind, COUNT(*) FROM lingxing_sync_diff WHERE run_id = ? GROUP BY kind", (d["id"],)).fetchall()}
            out.append(d)
    return out


def get_lingxing_sync_run(run_id: int) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM lingxing_sync_run WHERE id = ?",
            (int(run_id),),
        ).fetchone()
    if not row:
        return None
    return {k: row[k] for k in row.keys()}


def mark_lingxing_sync_run_status(run_id: int, status: str, error: Optional[str] = None) -> None:
    with _connect() as conn:
        if error is None:
            conn.execute(
                "UPDATE lingxing_sync_run SET status = ? WHERE id = ?",
                (status, int(run_id)),
            )
        else:
            conn.execute(
                "UPDATE lingxing_sync_run SET status = ?, error = ? WHERE id = ?",
                (status, error, int(run_id)),
            )
        conn.commit()


def replace_lingxing_preview(
    run_id: int,
    sku_rows: List[Dict[str, Any]],
    field_rows: List[Dict[str, Any]],
) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM lingxing_sync_preview_field WHERE run_id = ?", (int(run_id),))
        conn.execute("DELETE FROM lingxing_sync_preview_sku WHERE run_id = ?", (int(run_id),))
        uniq_skus: Dict[str, Dict[str, Any]] = {}
        for rec in sku_rows:
            sku = str(rec.get("sku") or "").strip()
            if sku:
                uniq_skus[sku] = rec
        conn.executemany(
            """
            INSERT INTO lingxing_sync_preview_sku (
                run_id, sku, is_new, group_kind, mismatch_skus, remote_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(run_id),
                    rec["sku"],
                    1 if rec.get("is_new") else 0,
                    rec.get("group_kind") or "unchanged",
                    rec.get("mismatch_skus") or "",
                    rec.get("remote_json") or "{}",
                )
                for rec in uniq_skus.values()
            ],
        )
        conn.executemany(
            """
            INSERT INTO lingxing_sync_preview_field (
                run_id, sku, field, local_value, remote_value, default_checked
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(run_id),
                    rec["sku"],
                    rec["field"],
                    rec.get("local_value"),
                    rec.get("remote_value"),
                    1 if rec.get("default_checked") else 0,
                )
                for rec in field_rows
            ],
        )
        conn.commit()


def list_lingxing_preview_skus(run_id: int) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT run_id, sku, is_new, group_kind, mismatch_skus, remote_json
            FROM lingxing_sync_preview_sku
            WHERE run_id = ?
            ORDER BY group_kind, sku COLLATE NOCASE
            """,
            (int(run_id),),
        ).fetchall()
    return [{k: row[k] for k in row.keys()} for row in rows]


def list_lingxing_preview_fields(run_id: int) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT sku, field, local_value, remote_value, default_checked
            FROM lingxing_sync_preview_field
            WHERE run_id = ?
            ORDER BY id
            """,
            (int(run_id),),
        ).fetchall()
    return [
        {
            "sku": r["sku"],
            "field": r["field"],
            "local_value": r["local_value"] or "",
            "remote_value": r["remote_value"] or "",
            "default_checked": bool(r["default_checked"]),
        }
        for r in rows
    ]
