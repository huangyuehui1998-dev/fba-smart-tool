"""领星数据适配：MCP 返回 / 后台导出 Excel/CSV → 产品库字段（共用一套映射）。

映射在 backend/config/lingxing_field_map.json（app_data/config 下同名文件可覆盖）。
申报价来源（v8 E1）：亚马逊实时售价 listing_price，以领星为准。
"""
from __future__ import annotations

import json
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from fba_tool.app_paths import resolve_config_read

FIELD_MAP_FILE = "lingxing_field_map.json"


@lru_cache(maxsize=1)
def load_field_map() -> Dict[str, Any]:
    path = resolve_config_read(FIELD_MAP_FILE)
    return json.loads(path.read_text(encoding="utf-8"))


def _pick(row: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            return v
    return None


def _keys(field: str) -> List[str]:
    fm = load_field_map()
    return list(fm["listing"].get(field, [])) + list(fm.get("excel_headers", {}).get(field, []))


# S9-step2-fix2 N2：价格上限（美元）。超过就视为无效价格，不写入、给提示。
# S9-step3 #6：改为可配置——设置参数 price_max（出厂值在 backend/config/user_settings.default.json 和
# user_config.DEFAULT_SETTINGS 的 parameters.price_max；用户改 app_data/config/user_settings.json 或设置页“参数”）。
# PRICE_MAX 保留为出厂默认值（兼容旧引用）；实际判断一律用 price_max()。
PRICE_MAX = 100000.0


def price_max() -> float:
    """当前价格上限：取设置参数 price_max；没配、不是正的有限数字时用出厂值 PRICE_MAX。"""
    import math

    try:
        from fba_tool.user_config import param

        v = float(param("price_max", PRICE_MAX))
    except Exception:  # noqa: BLE001  配置坏了不影响解析，用出厂值
        return PRICE_MAX
    return v if math.isfinite(v) and v > 0 else PRICE_MAX
# N1：逗号只接受标准千分位（1,299.00）；其余带逗号的写法（12,5 / 1.299,00 / 1,2,3）一律无效，不猜。
_THOUSANDS_RE = re.compile(r"^\d{1,3}(,\d{3})+(\.\d+)?$")
# N3：普通小数，不接受科学计数法（1e3、1e-3）、正负号、十六进制等
_PLAIN_RE = re.compile(r"^(\d+(\.\d*)?|\.\d+)$")
_PRICE_PREFIXES = ("USD$", "US$", "USD", "$")


def parse_price_reason(value: Any) -> Tuple[Optional[float], str]:
    """统一价格解析（预览、定时同步、Excel 导入都用它）。返回 (价格, 无效原因)；有效时原因为 ""。

    规则：可带前缀 $ / US$ / USD；逗号只按标准千分位接受；不接受科学计数法；
    四舍五入到分（ROUND_HALF_UP，与报关 customs_package.money_half_up、发票 invoice_rules.round2 一致，S9-step3）后必须 > 0；
    不超过 price_max()。任何异常输入都不抛异常（含 OverflowError、decimal.InvalidOperation）。"""
    if value is None or isinstance(value, bool):
        return None, ("" if value is None else "不是数字")
    try:
        if isinstance(value, float) and value != value:
            return None, "不是数字"
        if isinstance(value, (int, float)):
            # S9-step3：Excel 数值单元格（如 1e-05、1e16）不是用户写的科学计数法，按数值判断，不提示“科学计数法”
            if value in (float("inf"), float("-inf")):
                return None, "不是数字"
            return _check_decimal(Decimal(str(value)))
        text = unicodedata.normalize("NFKC", str(value)).strip()
        if not text:
            return None, ""
        upper = text.upper()
        for p in _PRICE_PREFIXES:
            if upper.startswith(p):
                text = text[len(p):].strip()
                break
        if "," in text:
            if not _THOUSANDS_RE.match(text):
                return None, "逗号写法不规范（疑似欧式写法，如 12,5 / 1.299,00），不猜测"
            text = text.replace(",", "")
        if not _PLAIN_RE.match(text):
            low = text.lower()
            if re.match(r"^[\d.]+e[+-]?\d+$", low):
                return None, "不接受科学计数法"
            if text.startswith("-"):
                return None, "不是大于 0 的数字"
            return None, "不是数字"
        return _check_decimal(Decimal(text))
    except (InvalidOperation, OverflowError, ValueError, TypeError, ArithmeticError):
        return None, "不是数字"


def _check_decimal(d: Decimal) -> Tuple[Optional[float], str]:
    """范围检查 + 舍入到分（ROUND_HALF_UP）。"""
    if d <= 0:
        return None, "不是大于 0 的数字"
    cap = price_max()
    if d > Decimal(str(cap)):
        return None, f"超过价格上限 {cap:g}"
    q = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)  # S9-step3：12.005 → 12.01，0.005 → 0.01
    if q <= 0:
        return None, "不是大于 0 的数字（四舍五入到分后为 0）"
    return float(q), ""


def parse_price(value: Any) -> Optional[float]:
    """价格：见 parse_price_reason；无效返回 None（不静默填 0）。"""
    return parse_price_reason(value)[0]


_CURRENCY_SYMBOLS = {
    "$": "USD", "US$": "USD", "US $": "USD", "USD$": "USD",
    "C$": "CAD", "CA$": "CAD", "A$": "AUD", "AU$": "AUD", "MX$": "MXN",
    "€": "EUR", "£": "GBP", "¥": "JPY", "￥": "JPY", "₹": "INR",
}


def normalize_currency(value: Any) -> Optional[str]:
    """币种统一成 ISO 4217 代码：符号（如 "$"）按映射转换，3 位字母转大写；空值返回 None。"""
    text = str(value or "").strip()
    if not text:
        return None
    if text in _CURRENCY_SYMBOLS:
        return _CURRENCY_SYMBOLS[text]
    up = text.upper()
    if up in _CURRENCY_SYMBOLS:
        return _CURRENCY_SYMBOLS[up]
    if len(up) == 3 and up.isalpha():
        return up
    raise ValueError(f"无法识别的币种：{text}")


def _safe_currency(cur: Any) -> str:
    try:
        return normalize_currency(cur) or "USD"
    except ValueError:
        return str(cur).strip().upper()  # 未知币种原样保留，不冒充 USD


def map_listing_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sku = _pick(row, _keys("sku"))
    if sku in (None, ""):
        return None
    price = None
    basis = None
    issues: List[Dict[str, str]] = []
    for k in _keys("listing_price"):
        raw = row.get(k)
        price, reason = parse_price_reason(raw)
        if price is not None:
            basis = k
            break
        if reason:  # N1–N3：单行价格无效只记提示，不中止整批
            item = {"field": "listing_price", "key": k, "raw": str(raw)[:40], "reason": reason}
            # S9-step3 #3：多个售价别名键里放了同一个坏值时只记一次（按 field + 原值 + 原因去重）
            if not any((i["field"], i["raw"], i["reason"]) == (item["field"], item["raw"], item["reason"]) for i in issues):
                issues.append(item)
    cur = _pick(row, _keys("listing_price_currency"))
    out = {
        "sku": str(sku).strip(),
        "fnsku": str(_pick(row, _keys("fnsku")) or "").strip(),
        "asin": str(_pick(row, _keys("asin")) or "").strip(),
        "local_sku": str(_pick(row, _keys("local_sku")) or "").strip(),
        "listing_price": price,
        "listing_price_currency": _safe_currency(cur) if price is not None else None,
        "local_name": str(_pick(row, _keys("local_name")) or "").strip(),
        "listing_price_basis": basis,
    }
    if issues and price is None:  # 有一个价格字段可用就不提示（与原来“取第一个可用价格”一致）
        out["price_issues"] = issues
    return out


def get_listing_price(sku: str) -> Optional[float]:
    """申报价接口（v8 E1）：返回产品库里领星同步/导入的实时售价。

    首期数据来自领星 Excel/CSV 导入或 MCP 预览确认；接上定时同步（S5）后由同步刷新，调用方不用改。
    """
    from fba_tool.master_db import get_product_by_sku

    rec = get_product_by_sku(str(sku or "").strip())
    if not rec:
        return None
    return rec.get("listing_price")
