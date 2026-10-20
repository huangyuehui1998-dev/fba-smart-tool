"""申报价口径、汇率快照、领星售价两层导入。

金额先按整票本币合计，再一次性换算。禁止逐行把单价换成美元后再乘件数。
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence

from openpyxl import load_workbook

from fba_tool.customs_package import money_half_up, to_dec

US_TOKENS = {"美国", "美国站", "US", "USA", "UNITED STATES", "AMAZON.COM"}
NON_US_TOKENS = {"加拿大", "加拿大站", "CA", "CANADA", "CAD"}
FOB_NOTICE = "该值为零售价口径，非 FOB（取自历史申报价）"
TARGET_PAIR = "USD/CNY"


class FxRateRequired(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "FX_RATE_REQUIRED"
        self.message = message


def _num(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        number = to_dec(value)
    except Exception:
        return None
    if number != number:
        return None
    return number


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def snapshot_from_row(row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    row = row or {}
    return {
        "fx_rate": row.get("rate"),
        "fx_rate_type": row.get("rate_type") or "",
        "fx_applicable_month": row.get("applicable_month") or "",
        "fx_source_url": row.get("source_url") or "",
        "fx_publish_date": row.get("publish_date") or "",
    }


def require_fx(snapshot: Optional[Dict[str, Any]], month: str, pair: str = TARGET_PAIR) -> Dict[str, Any]:
    snap = dict(snapshot or {})
    rate = _num(snap.get("fx_rate"))
    if rate is None or rate <= 0:
        label = "USD/CNY" if pair == TARGET_PAIR else pair.replace("/", "→")
        if pair != TARGET_PAIR:
            left, _, right = pair.partition("/")
            label = f"{left}→{right}"
        raise FxRateRequired(f"缺 {month} {label} 汇率，请在 Step5 录入后再导出")
    snap["fx_rate"] = float(rate)
    return snap


def to_usd(amount: Any, currency: str, fx_rate: Any) -> Decimal:
    cur = str(currency or "").strip().upper()
    if cur in ("", "USD"):
        return money_half_up(amount)
    rate = _num(fx_rate)
    if rate is None or rate <= 0:
        raise FxRateRequired("汇率缺失或小于等于 0")
    return money_half_up(to_dec(amount) / rate)


def convert_fob(amount: Any, currency: str, declared_currency: str, fx_rate: Any) -> Decimal:
    src = str(currency or "").strip().upper()
    dst = str(declared_currency or "USD").strip().upper()
    if src == dst:
        return money_half_up(amount)
    if src not in {"CNY", "USD"} or dst not in {"CNY", "USD"}:
        raise ValueError("暂不支持该币种")
    rate = _num(fx_rate)
    if rate is None or rate <= 0:
        raise FxRateRequired("汇率缺失或小于等于 0")
    if src == "CNY" and dst == "USD":
        return money_half_up(to_dec(amount) / rate)
    if src == "USD" and dst == "CNY":
        return money_half_up(to_dec(amount) * rate)
    raise ValueError("暂不支持该币种")


def _line_amounts(cny_lines: Sequence[Decimal], fx: Decimal) -> tuple[Decimal, List[Decimal]]:
    total_cny = sum(cny_lines, Decimal("0"))
    total_usd = money_half_up(total_cny / fx)
    amounts: List[Decimal] = []
    running = Decimal("0")
    for index, cny in enumerate(cny_lines):
        if index < len(cny_lines) - 1:
            amt = money_half_up(cny / fx)
            running += amt
            amounts.append(amt)
        else:
            amounts.append(money_half_up(total_usd - running))
    return total_cny, amounts


def quote_declared_value(
    lines: Sequence[Dict[str, Any]],
    basis: str,
    fx_snapshot: Optional[Dict[str, Any]],
    *,
    month: str,
    min_retail_ratio: Any = Decimal("0.30"),
) -> Dict[str, Any]:
    """lines: sku, qty, retail_usd, purchase_cny, fob_value, fob_currency, legacy_usd。"""
    mode = str(basis or "retail").strip().lower()
    if mode not in {"retail", "fob", "cost"}:
        raise ValueError(f"申报价口径只能是 retail / fob / cost：{basis}")
    needs_fx = mode in {"cost", "fob"} or any(
        str(line.get("fob_currency") or "USD").upper() not in {"", "USD"} for line in lines
    )
    if mode == "retail":
        needs_fx = any(str(line.get("retail_currency") or "USD").upper() not in {"", "USD"} for line in lines)
    snap = dict(fx_snapshot or {})
    if needs_fx or mode != "retail":
        if mode == "retail" and not needs_fx:
            pass
        else:
            snap = require_fx(snap, month)
    fx = _num(snap.get("fx_rate")) or Decimal("0")
    ratio = to_dec(min_retail_ratio or "0.30")
    out_lines: List[Dict[str, Any]] = []
    notices: List[str] = []
    warnings: List[str] = []
    total_qty = 0
    if mode == "cost":
        cny_lines = [to_dec(line.get("qty")) * to_dec(line.get("purchase_cny")) for line in lines]
        total_cny, amounts = _line_amounts(cny_lines, fx)
    elif mode == "fob":
        manual = []
        missing_manual = False
        for line in lines:
            if line.get("fob_value") in (None, ""):
                missing_manual = True
                break
            manual.append(convert_fob(line.get("fob_value"), str(line.get("fob_currency") or "USD"), "USD", fx) * to_dec(line.get("qty")))
        if missing_manual:
            amounts = [money_half_up(to_dec(line.get("legacy_usd")) * to_dec(line.get("qty"))) for line in lines]
            total_cny = None
            notices.append(FOB_NOTICE)
        else:
            total = money_half_up(sum(manual, Decimal("0")))
            amounts = []
            running = Decimal("0")
            for index, amt in enumerate(manual):
                if index < len(manual) - 1:
                    rounded = money_half_up(amt)
                    running += rounded
                    amounts.append(rounded)
                else:
                    amounts.append(money_half_up(total - running))
            total_cny = None
    else:
        amounts = [money_half_up(to_dec(line.get("retail_usd")) * to_dec(line.get("qty"))) for line in lines]
        total_cny = None
    total_usd = money_half_up(sum(amounts, Decimal("0")))
    for line, amount in zip(lines, amounts):
        qty = int(to_dec(line.get("qty")))
        total_qty += qty
        unit = money_half_up(amount / qty) if qty else Decimal("0")
        retail = _num(line.get("retail_usd"))
        purchase = _num(line.get("purchase_cny"))
        flags: List[str] = []
        if purchase is not None and fx > 0 and unit < money_half_up(purchase / fx):
            flags.append("申报价低于采购价")
        if retail is not None and retail > 0 and unit < money_half_up(retail * ratio):
            flags.append("申报价低于售价 30%")
        if retail is not None and unit > retail:
            flags.append("申报价高于售价")
        warnings.extend(flags)
        out_lines.append({
            "sku": line.get("sku"),
            "qty": qty,
            "amount_usd": float(amount),
            "unit_usd": float(unit),
            "currency": "USD",
            "warnings": flags,
        })
    avg = money_half_up(total_usd / total_qty) if total_qty else Decimal("0")
    blob = repr({"total": float(total_usd), "lines": out_lines})
    if "1021.76" in blob:
        raise AssertionError("逐行换算产生了 1021.76")
    return {
        "basis": mode,
        "currency": "USD",
        "total_cny": None if total_cny is None else float(money_half_up(total_cny)),
        "total_usd": float(total_usd),
        "avg_usd": float(avg),
        "lines": out_lines,
        "warnings": warnings,
        "fob_source_notice": FOB_NOTICE if FOB_NOTICE in notices else "",
        **snapshot_from_row({
            "rate": snap.get("fx_rate"),
            "rate_type": snap.get("fx_rate_type"),
            "applicable_month": snap.get("fx_applicable_month") or month,
            "source_url": snap.get("fx_source_url"),
            "publish_date": snap.get("fx_publish_date"),
        }),
    }


def is_target_site(country: Any = "", marketplace: Any = "") -> bool:
    text = str(country or "").strip()
    market = str(marketplace or "").strip()
    blob = f"{text} {market}".upper()
    tokens = {text.upper(), market.upper()}
    if tokens & {item.upper() for item in NON_US_TOKENS} or "加拿大" in text or "CANADA" in blob:
        return False
    if "美国" in text or tokens & {"US", "USA", "UNITED STATES"} or "AMAZON.COM" in blob:
        return True
    return False


def price_from_chain(price: Any, landed: Any, shipping: Any) -> Optional[Decimal]:
    primary = _num(price)
    if primary is not None and primary > 0:
        return primary
    landed_n = _num(landed)
    if landed_n is None or landed_n <= 0:
        return None
    ship = _num(shipping) or Decimal("0")
    net = landed_n - ship
    if net <= 0:
        return None
    return net


def _header_map(headers: Sequence[Any]) -> Dict[str, int]:
    found: Dict[str, int] = {}
    for index, header in enumerate(headers):
        key = str(header or "").strip()
        if key:
            found[key] = index
    return found


def parse_listing_table(headers: Sequence[Any], rows: Iterable[Sequence[Any]]) -> List[Dict[str, Any]]:
    mapped = _header_map(headers)
    if "MSKU" not in mapped:
        raise ValueError("缺必要列：MSKU")
    if "价格" not in mapped and "售价(总价)" not in mapped:
        raise ValueError("缺必要列：价格与售价(总价)")
    if "币种" not in mapped:
        raise ValueError("缺必要列：币种")
    parsed: List[Dict[str, Any]] = []
    for raw in rows:
        cells = list(raw)

        def cell(name: str) -> Any:
            idx = mapped.get(name)
            if idx is None or idx >= len(cells):
                return None
            return cells[idx]

        parsed.append({
            "msku": str(cell("MSKU") or "").strip(),
            "country": cell("国家"),
            "currency": cell("币种"),
            "price": cell("价格"),
            "landed_price": cell("售价(总价)"),
            "shipping": cell("运费"),
            "fnsku": cell("FNSKU"),
        })
    return parsed


def parse_listing_xlsx(data: bytes) -> List[Dict[str, Any]]:
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    ws = wb.worksheets[0]
    body = list(ws.iter_rows(values_only=True))
    if not body:
        raise ValueError("文件无法解析")
    return parse_listing_table(body[0], body[1:])


def import_retail_rows(
    rows: Sequence[Dict[str, Any]],
    products: Dict[str, Dict[str, Any]],
    *,
    source: str,
    fx_by_pair: Optional[Dict[str, Any]] = None,
    synced_at: Optional[str] = None,
) -> Dict[str, Any]:
    """站点过滤后再匹配产品库。非美国站即使有汇率也不写入。"""
    fx_by_pair = fx_by_pair or {}
    parsed: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    warnings: List[str] = []
    for row in rows:
        msku = str(row.get("msku") or row.get("MSKU") or "").strip()
        if not msku:
            skipped.append({"msku": "", "reason": "缺少 MSKU"})
            continue
        if not is_target_site(row.get("country") or row.get("国家"), row.get("marketplace")):
            skipped.append({"msku": msku, "reason": "非目标站点"})
            continue
        currency = str(row.get("currency") if row.get("currency") is not None else row.get("币种") or "").strip()
        if not currency:
            skipped.append({"msku": msku, "reason": "币种为空"})
            continue
        amount = price_from_chain(
            row.get("price", row.get("价格")),
            row.get("landed_price", row.get("售价(总价)")),
            row.get("shipping", row.get("运费")),
        )
        if amount is None:
            skipped.append({"msku": msku, "reason": "价格链无值"})
            continue
        cur = currency.upper()
        if cur != "USD":
            pair = f"{cur}/USD"
            rate = fx_by_pair.get(pair)
            if _num(rate) is None or _num(rate) <= 0:
                raise FxRateRequired(f"美国站行缺 {cur}→USD 汇率")
            usd = to_usd(amount, cur, rate)
        else:
            usd = money_half_up(amount)
        item = {"msku": msku, "price_usd": float(usd), "currency": "USD", "raw_currency": cur}
        parsed.append(item)
        product = products.get(msku)
        fnsku = str(row.get("fnsku") or row.get("FNSKU") or "").strip()
        if product and fnsku and str(product.get("fnsku") or "").strip() and fnsku != str(product.get("fnsku")).strip():
            warnings.append(f"{msku} FNSKU 不一致：表内 {fnsku}，产品库 {product.get('fnsku')}")
    imported = []
    unmatched = []
    for item in parsed:
        if item["msku"] in products:
            imported.append(item)
        else:
            unmatched.append({**item, "reason": "MSKU 未匹配产品库"})
    prices = {item["msku"]: item["price_usd"] for item in imported}
    return {
        "parsed": parsed,
        "parsed_count": len(parsed),
        "imported": imported,
        "imported_count": len(imported),
        "unmatched": unmatched,
        "unmatched_count": len(unmatched),
        "skipped": skipped,
        "prices": prices,
        "warnings": warnings,
        "retail_source": source,
        "retail_synced_at": synced_at or _now(),
    }


def resolve_retail(
    products: Dict[str, Dict[str, Any]],
    *,
    mcp_rows: Optional[Sequence[Dict[str, Any]]] = None,
    xlsx_rows: Optional[Sequence[Dict[str, Any]]] = None,
    fx_by_pair: Optional[Dict[str, Any]] = None,
    mcp_error: Optional[str] = None,
) -> Dict[str, Any]:
    if mcp_error:
        result = import_retail_rows(xlsx_rows or [], products, source="manual_xlsx", fx_by_pair=fx_by_pair)
        result["notice"] = "领星同步失败，已用手动导入值"
        result["mcp_error"] = mcp_error
        return result
    return import_retail_rows(mcp_rows or [], products, source="lingxing_mcp", fx_by_pair=fx_by_pair)


def product_cost_usd(cny: Any, fx_rate: Any) -> Decimal:
    return money_half_up(to_dec(cny) / to_dec(fx_rate))


def sta_fee_comparison(estimate_min: Any, estimate_max: Any, entered: Any) -> Dict[str, Any]:
    low = float(estimate_min)
    high = float(estimate_max)
    actual = float(entered)
    return {
        "estimate_min_usd": low,
        "estimate_max_usd": high,
        "sta_placement_fee": actual,
        "out_of_range": actual < low or actual > high,
    }


_FBA_RE = re.compile(r"^FBA")


def record_sta_placement_fee(fba_id: str, entered: Any, estimate_min: Any, estimate_max: Any) -> Dict[str, Any]:
    from fba_tool.ticket_import import set_ticket_fields

    compared = sta_fee_comparison(estimate_min, estimate_max, entered)
    key = str(fba_id or "").strip().upper()
    if _FBA_RE.match(key):
        set_ticket_fields(key, {"sta_placement_fee": compared["sta_placement_fee"]}, "manual")
    compared["fba_id"] = key
    return compared
