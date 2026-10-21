"""计征汇率。月份按报关完成申报之日，不回退到上一个月。"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

CUSTOMS_MONTHLY_SOURCE = (
    "CFETS 人民币汇率中间价，上月第三个星期三；非银行间外汇市场交易日顺延到下一交易日"
)
TAX_FX_SALE_DAY = "销售额发生当日"
TAX_FX_MONTH_FIRST = "当月 1 日"
TAX_FX_CHOICES = {
    "sale_day": TAX_FX_SALE_DAY,
    "month_first": TAX_FX_MONTH_FIRST,
    TAX_FX_SALE_DAY: TAX_FX_SALE_DAY,
    TAX_FX_MONTH_FIRST: TAX_FX_MONTH_FIRST,
    "当月 1 日有效的中间价": TAX_FX_MONTH_FIRST,
}


def customs_month(declaration_date: str) -> str:
    """署令第 272 号第十四条：适用完成申报之日所在月，不按发货日或导出日。"""
    text = str(declaration_date or "").strip()[:10]
    if len(text) < 7 or text[4] != "-":
        raise ValueError("报关完成申报之日不合法")
    datetime.strptime(text, "%Y-%m-%d")
    return text[:7]


def _conn():
    from fba_tool.warehouse_db import _conn as connect

    return connect()


def ensure_fx_columns() -> None:
    with _conn() as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(fx_rate)").fetchall()}
        if "source" not in cols:
            conn.execute("ALTER TABLE fx_rate ADD COLUMN source TEXT")
        conn.commit()


def list_rates() -> List[Dict[str, Any]]:
    ensure_fx_columns()
    with _conn() as conn:
        cur = conn.execute(
            "SELECT * FROM fx_rate ORDER BY applicable_month, currency_pair, rate_type"
        )
        names = [item[0] for item in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]


def upsert_rate(body: Dict[str, Any]) -> Dict[str, Any]:
    ensure_fx_columns()
    pair = str(body.get("currency_pair") or "USD/CNY").strip().upper()
    rate_type = str(body.get("rate_type") or "customs_monthly").strip()
    month = str(body.get("applicable_month") or "").strip()
    if len(month) != 7 or month[4] != "-":
        raise ValueError("适用月份须为 YYYY-MM")
    rate = float(body["rate"])
    if rate <= 0:
        raise ValueError("汇率必须大于 0")
    source = str(body.get("source") or "")
    if rate_type == "customs_monthly" and not source:
        source = CUSTOMS_MONTHLY_SOURCE
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO fx_rate
               (currency_pair, rate, rate_type, applicable_month, publish_date, source_url, source_note, source, entered_by, entered_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(currency_pair, rate_type, applicable_month) DO UPDATE SET
                 rate=excluded.rate, publish_date=excluded.publish_date, source_url=excluded.source_url,
                 source_note=excluded.source_note, source=excluded.source, entered_by=excluded.entered_by,
                 entered_at=excluded.entered_at""",
            (
                pair, rate, rate_type, month,
                body.get("publish_date") or "",
                body.get("source_url") or "",
                body.get("source_note") or "",
                source,
                body.get("entered_by") or "",
                now,
            ),
        )
        conn.commit()
    found = get_rate(pair, rate_type, month)
    if not found:
        raise ValueError("汇率没有写入")
    return found


def get_rate(pair: str, rate_type: str, month: str) -> Optional[Dict[str, Any]]:
    ensure_fx_columns()
    with _conn() as conn:
        cur = conn.execute(
            """SELECT * FROM fx_rate
               WHERE currency_pair = ? AND rate_type = ? AND applicable_month = ?""",
            (pair, rate_type, month),
        )
        row = cur.fetchone()
        if not row:
            return None
        return dict(zip([item[0] for item in cur.description], row))


def delete_rate(rate_id: int) -> bool:
    ensure_fx_columns()
    with _conn() as conn:
        cur = conn.execute("DELETE FROM fx_rate WHERE id = ?", (int(rate_id),))
        conn.commit()
        return cur.rowcount > 0


def snapshot_for_declaration(
    declaration_date: str,
    *,
    rate_type: str = "customs_monthly",
    pair: str = "USD/CNY",
    fx_snapshot: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """只取申报日所在月。快照月份一致时沿用快照，否则查表，缺了不改用别的月份。"""
    month = customs_month(declaration_date)
    snap = dict(fx_snapshot or {})
    snap_month = str(snap.get("fx_applicable_month") or snap.get("applicable_month") or "")
    snap_rate = snap.get("fx_rate", snap.get("rate"))
    if snap_month == month and snap_rate not in (None, "", 0):
        snap["fx_applicable_month"] = month
        snap.setdefault("fx_rate_type", rate_type)
        return snap
    row = get_rate(pair, rate_type, month)
    if not row:
        return None
    return {
        "fx_rate": row["rate"],
        "fx_rate_type": row["rate_type"],
        "fx_applicable_month": month,
        "fx_source_url": row.get("source_url") or "",
        "fx_publish_date": row.get("publish_date") or "",
        "fx_source": row.get("source") or CUSTOMS_MONTHLY_SOURCE,
    }


def import_csv(data: bytes) -> Dict[str, Any]:
    text = data.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    written = []
    for row in rows:
        written.append(upsert_rate(row))
    return {"imported": len(written), "items": written}
