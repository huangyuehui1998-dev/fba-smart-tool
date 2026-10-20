"""领星店铺、库存、同步记录与发票提示。从 master_db 拆出，经 master_db 再导出。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fba_tool.master_db import _connect, _opt_int, _opt_str

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
