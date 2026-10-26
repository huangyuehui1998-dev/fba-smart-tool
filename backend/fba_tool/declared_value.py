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


class MissingPrice(Exception):
    def __init__(self, missing: List[Dict[str, Any]]) -> None:
        skus = "、".join(str(item.get("sku") or "") for item in missing)
        message = f"以下 SKU 缺申报价：{skus}，请在产品库补齐"
        super().__init__(message)
        self.code = "DECLARED_VALUE_MISSING"
        self.message = message
        self.missing = missing


class InvalidFx(ValueError):
    """汇率参数不是数字，也不是带数字 fx_rate 的对象。"""


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


def _strict_num(value: Any) -> Optional[Decimal]:
    """金额路径：None 不是 0。非数字字符串交给调用方当成汇率非法。"""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            Decimal(text)
        except Exception as exc:
            raise InvalidFx("汇率不合法") from exc
    return _num(value)


def normalize_fx(fx_snapshot: Any, month: str = "") -> Dict[str, Any]:
    """fx 可以是数字，也可以是带 fx_rate 的对象。不合法时抛 InvalidFx，不抛 500。"""
    if isinstance(fx_snapshot, (int, float, Decimal)):
        return {"fx_rate": fx_snapshot, "fx_applicable_month": month}
    if isinstance(fx_snapshot, str):
        rate = _strict_num(fx_snapshot)
        if rate is None:
            raise InvalidFx("汇率不合法")
        return {"fx_rate": rate, "fx_applicable_month": month}
    if fx_snapshot is None:
        return {}
    if not isinstance(fx_snapshot, dict):
        raise InvalidFx("汇率不合法")
    snap = dict(fx_snapshot)
    if "fx_rate" in snap and snap.get("fx_rate") not in (None, ""):
        _strict_num(snap.get("fx_rate"))
    return snap


def _positive(value: Any) -> Optional[Decimal]:
    number = _num(value)
    if number is None or number <= 0:
        return None
    return number


def _qty_of(line: Dict[str, Any]) -> int:
    qty = _num(line.get("qty"))
    if qty is None or qty <= 0:
        raise MissingPrice([{
            "sku": line.get("sku") or "",
            "basis": "",
            "tried": ["qty"],
        }])
    return int(qty)


def _purchase_cny(line: Dict[str, Any]) -> Optional[Decimal]:
    if line.get("purchase_price_cny") not in (None, ""):
        return _positive(line.get("purchase_price_cny"))
    if line.get("purchase_cny") not in (None, ""):
        return _positive(line.get("purchase_cny"))
    return None


def _resolve_line(
    line: Dict[str, Any],
    mode: str,
    fx: Optional[Decimal],
    domestic_rate: Decimal,
) -> Dict[str, Any]:
    """逐行回退。返回 unit、currency（USD 或 CNY）、price_source、notices。"""
    sku = str(line.get("sku") or "")
    tried: List[str] = []
    if mode == "retail":
        tried.append("lingxing")
        retail = _positive(line.get("retail_usd"))
        if retail is not None:
            return {"unit": retail, "currency": "USD", "price_source": "lingxing", "notices": []}
        tried.append("manual")
        manual = _positive(line.get("manual_usd"))
        if manual is not None:
            return {"unit": manual, "currency": "USD", "price_source": "manual", "notices": []}
        tried.append("legacy")
        legacy = _positive(line.get("legacy_usd"))
        if legacy is not None:
            return {"unit": legacy, "currency": "USD", "price_source": "legacy", "notices": []}
        tried.append("product_cost")
        cost = _positive(line.get("product_cost_cny"))
        if cost is not None:
            if fx is None or fx <= 0:
                raise FxRateRequired("汇率缺失或小于等于 0")
            return {
                "unit": money_half_up(cost / fx),
                "currency": "USD",
                "price_source": "product_cost",
                "notices": [],
            }
    elif mode == "cost":
        tried.append("purchase")
        purchase = _purchase_cny(line)
        if purchase is not None:
            return {"unit": purchase, "currency": "CNY", "price_source": "purchase", "notices": []}
    else:
        tried.append("manual_fob")
        if line.get("fob_value") not in (None, ""):
            unit = convert_fob(line.get("fob_value"), str(line.get("fob_currency") or "USD"), "USD", fx)
            return {"unit": unit, "currency": "USD", "price_source": "manual_fob", "notices": []}
        tried.append("legacy")
        legacy = _positive(line.get("legacy_usd"))
        if legacy is not None:
            return {"unit": legacy, "currency": "USD", "price_source": "legacy", "notices": [FOB_NOTICE]}
        tried.append("purchase")
        purchase = _purchase_cny(line)
        if purchase is not None:
            if fx is None or fx <= 0:
                raise FxRateRequired("汇率缺失或小于等于 0")
            factor = Decimal("1") + domestic_rate
            return {
                "unit": money_half_up(purchase * factor / fx),
                "currency": "USD",
                "price_source": "purchase",
                "notices": [],
            }
    raise MissingPrice([{"sku": sku, "basis": mode, "tried": tried}])


def quote_declared_value(
    lines: Sequence[Dict[str, Any]],
    basis: str,
    fx_snapshot: Any = None,
    *,
    month: str,
    min_retail_ratio: Any = Decimal("0.30"),
    fob_domestic_cost_rate: Any = 0,
) -> Dict[str, Any]:
    """逐行决定单价来源。算不出则整次报价失败，不允许把缺价当成 0.00。"""
    mode = str(basis or "retail").strip().lower()
    if mode not in {"retail", "fob", "cost"}:
        raise ValueError(f"申报价口径只能是 retail / fob / cost：{basis}")
    snap = normalize_fx(fx_snapshot, month)
    domestic = _num(fob_domestic_cost_rate)
    if domestic is None:
        domestic = Decimal("0")
    fx = _num(snap.get("fx_rate"))
    resolved: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    for line in lines:
        try:
            resolved.append(_resolve_line(line, mode, fx, domestic))
        except MissingPrice as exc:
            missing.extend(exc.missing)
    if missing:
        raise MissingPrice(missing)
    needs_fx = mode == "cost" or any(item["currency"] == "CNY" or item["price_source"] == "purchase" for item in resolved)
    if mode == "fob" and any(str(line.get("fob_currency") or "USD").upper() not in {"", "USD"} for line in lines):
        needs_fx = True
    if needs_fx:
        snap = require_fx(snap, month)
        fx = _num(snap.get("fx_rate"))
    ratio = to_dec(min_retail_ratio or "0.30")
    notices: List[str] = []
    warnings: List[str] = []
    total_qty = 0
    total_cny: Optional[Decimal] = None
    if mode == "cost":
        cny_lines = []
        for line, item in zip(lines, resolved):
            cny_lines.append(_qty_of(line) * item["unit"])
        total_cny, amounts = _line_amounts(cny_lines, fx or Decimal("1"))
    else:
        raw_amounts = []
        for line, item in zip(lines, resolved):
            raw_amounts.append(item["unit"] * _qty_of(line))
            notices.extend(item["notices"])
        total = money_half_up(sum(raw_amounts, Decimal("0")))
        amounts = []
        running = Decimal("0")
        for index, amt in enumerate(raw_amounts):
            if index < len(raw_amounts) - 1:
                rounded = money_half_up(amt)
                running += rounded
                amounts.append(rounded)
            else:
                amounts.append(money_half_up(total - running))
    if mode != "cost":
        notices = []
        for item in resolved:
            notices.extend(item["notices"])
    total_usd = money_half_up(sum(amounts, Decimal("0")))
    if lines and total_usd <= 0:
        raise MissingPrice([{
            "sku": str(line.get("sku") or ""),
            "basis": mode,
            "tried": [resolved[index]["price_source"]],
        } for index, line in enumerate(lines)])
    out_lines: List[Dict[str, Any]] = []
    for line, item, amount in zip(lines, resolved, amounts):
        qty = _qty_of(line)
        total_qty += qty
        unit = money_half_up(amount / qty) if qty else Decimal("0")
        retail = _positive(line.get("retail_usd"))
        purchase = _purchase_cny(line)
        flags: List[str] = []
        if purchase is not None and fx is not None and fx > 0 and unit < money_half_up(purchase / fx):
            flags.append("申报价低于采购价")
        if retail is not None and unit < money_half_up(retail * ratio):
            flags.append("申报价低于售价 30%")
        if retail is not None and unit > retail:
            flags.append("申报价高于售价")
        line_notices = list(item["notices"])
        if item["price_source"] != "legacy":
            line_notices = [note for note in line_notices if "历史申报价" not in note]
        warnings.extend(flags)
        out_lines.append({
            "sku": line.get("sku"),
            "qty": qty,
            "amount_usd": float(amount),
            "unit_usd": float(unit),
            "currency": "USD",
            "price_source": item["price_source"],
            "notice": "；".join(line_notices),
            "warnings": flags,
        })
    avg = money_half_up(total_usd / total_qty) if total_qty else Decimal("0")
    legacy_notice = FOB_NOTICE if any(item["price_source"] == "legacy" and mode == "fob" for item in resolved) else ""
    return {
        "basis": mode,
        "currency": "USD",
        "total_cny": None if total_cny is None else float(money_half_up(total_cny)),
        "total_usd": float(total_usd),
        "avg_usd": float(avg),
        "lines": out_lines,
        "warnings": warnings,
        "fob_source_notice": legacy_notice,
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
    """零售导入（Accept C4 的换算路径）。先滤站点，再匹配产品库。

    美国站非 USD：用 fx_by_pair 里的「币种/USD」换成美元再写入；缺汇率或汇率 ≤ 0
    抛 FX_RATE_REQUIRED（路由层 409）。非美国站整行跳过（「非目标站点」），有汇率也不写。
    币种为空跳过，不默认 USD。

    领星 xlsx 预览不走这里。lingxing_listing_xlsx.parse_listing_xlsx 对已知站点的错币种
    只报「价格币种应为 USD/CAD」并跳过该行，不在 xlsx 路径上静默换汇。
    """
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


def persist_retail_import(
    rows: Sequence[Dict[str, Any]],
    *,
    source: str,
    fx_by_pair: Optional[Dict[str, Any]] = None,
    ignored_products: bool = False,
) -> Dict[str, Any]:
    """按产品库匹配后写回售价。未匹配的 SKU 不新建。"""
    from fba_tool.master_db import get_products_by_skus
    from fba_tool.product_fields import SOURCE_LINGXING, set_product_fields

    mskus = []
    for row in rows:
        msku = str(row.get("msku") or row.get("MSKU") or "").strip()
        if msku:
            mskus.append(msku)
    products = get_products_by_skus(mskus)
    result = import_retail_rows(rows, products, source=source, fx_by_pair=fx_by_pair)
    for item in result["imported"]:
        currency = str(item.get("currency") or "USD").upper()
        set_product_fields(
            item["msku"],
            {
                "listing_price": item["price_usd"],
                "listing_price_currency": currency,
                "retail_source": source,
                "retail_synced_at": result["retail_synced_at"],
            },
            SOURCE_LINGXING,
        )
    if ignored_products:
        result["warnings"] = list(result.get("warnings") or []) + ["products 参数已忽略，按产品库匹配"]
    return result


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
    amount = _num(cny)
    rate = _num(fx_rate)
    if amount is None or rate is None or rate <= 0:
        raise MissingPrice([{"sku": "", "basis": "retail", "tried": ["product_cost"]}])
    return money_half_up(amount / rate)


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
