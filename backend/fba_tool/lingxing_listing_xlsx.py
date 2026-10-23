"""领星网页 Listing 导出 → 预览。确认前不写 product_master。

不覆盖箱规和报关结构字段。美国站价格只收美元；采购成本只收人民币。
"""
from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional, Tuple

import openpyxl

from fba_tool.lingxing_preview import build_listing_preview
from fba_tool.master_db_lingxing import (
    add_lingxing_sync_diff,
    create_lingxing_sync_run,
    finish_lingxing_sync_run,
    tag_lingxing_sync_run,
)

_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")

_HEADER_MAP = {
    "msku": "msku",
    "fnsku": "fnsku",
    "asin": "asin",
    "父asin": "parent_asin",
    "状态": "status",
    "标题": "title",
    "店铺": "shop",
    "国家": "country",
    "配送方式": "fulfillment",
    "亚马逊品牌": "amazon_brand",
    "品名": "local_name",
    "sku": "local_sku",
    "分类": "category_name",
    "本地品牌": "local_brand",
    "币种": "currency",
    "售价(总价)": "total_price",
    "价格": "price",
    "优惠价": "sale_price",
    "list price": "list_price",
    "划线价": "strike_price",
    "预估fba费（api）": "fee_fba",
    "预估fba费(api)": "fee_fba",
    "平台费率": "referral_rate",
    "大类名称": "big_category",
    "采购成本": "purchase_cost",
    "成本": "purchase_cost",
    "成本币种": "cost_currency",
    "采购成本币种": "cost_currency",
}


def parse_listing_xlsx(data: bytes, filename: str = "", column_map: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    try:
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    if not rows:
        return {"products": [], "anomalies": [{"row": 0, "sku": "", "message": "空表"}], "warnings": [], "columns": []}
    headers = ["" if cell is None else str(cell).strip() for cell in rows[0]]
    mapping = _resolve_mapping(headers, column_map)
    products: List[Dict[str, Any]] = []
    anomalies: List[Dict[str, Any]] = []
    warnings: List[str] = []
    local_groups: Dict[str, List[str]] = {}
    for offset, raw in enumerate(rows[1:], start=2):
        if raw is None or all(cell in (None, "") for cell in raw):
            continue
        record = _row_dict(headers, raw, mapping)
        msku = str(record.get("msku") or "").strip()
        if not msku:
            anomalies.append({"row": offset, "sku": "", "message": "MSKU 为空，未导入"})
            continue
        site, expect = _site_currency(record.get("country"), record.get("shop"))
        currency = str(record.get("currency") or "").strip().upper()
        if expect and currency and currency != expect:
            anomalies.append({
                "row": offset,
                "sku": msku,
                "message": f"{site or '站点'} 价格币种应为 {expect}，文件里是 {currency}，该行不写入",
            })
            continue
        if expect and not currency:
            anomalies.append({"row": offset, "sku": msku, "message": "缺少币种，未写入"})
            continue
        built = _product(record, site or "", expect or currency or "USD")
        cost_issue = _purchase_cost(record, built)
        if cost_issue:
            anomalies.append({"row": offset, "sku": msku, "message": cost_issue})
        products.append(built)
        local_sku = str(built.get("local_sku") or "").strip()
        if local_sku:
            local_groups.setdefault(local_sku, []).append(msku)
    for local_sku, mskus in local_groups.items():
        uniq = list(dict.fromkeys(mskus))
        if len(uniq) > 1:
            warnings.append(f"本地 SKU {local_sku} 对应 {len(uniq)} 个 MSKU，两条都保留：{'、'.join(uniq)}")
    return {
        "products": products,
        "anomalies": anomalies,
        "warnings": warnings,
        "columns": headers,
        "mapping": {header: mapping[index] for index, header in enumerate(headers) if index in mapping},
        "export_at": export_at_from_name(filename),
    }


def export_at_from_name(filename: str) -> str:
    match = _DATE_RE.search(filename or "")
    return match.group(1) if match else ""


def build_xlsx_preview(data: bytes, filename: str, column_map: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    parsed = parse_listing_xlsx(data, filename, column_map)
    run_id = create_lingxing_sync_run()
    tag_lingxing_sync_run(run_id, "xlsx_import", 1)
    summary = build_listing_preview(run_id, parsed["products"])
    for item in parsed["anomalies"]:
        add_lingxing_sync_diff(run_id, "anomaly", str(item.get("sku") or ""), str(item.get("message") or ""))
    for text in parsed["warnings"]:
        add_lingxing_sync_diff(run_id, "warning", "", text)
    finish_lingxing_sync_run(run_id, "preview_pending", ["xlsx_import"], summary, None)
    from fba_tool.master_db_lingxing import set_lingxing_run_file_meta

    set_lingxing_run_file_meta(run_id, source_file=filename, export_at=parsed["export_at"])
    return {
        "run_id": run_id,
        "status": "preview_pending",
        "summary": summary,
        "anomalies": parsed["anomalies"],
        "warnings": parsed["warnings"],
        "columns": parsed["columns"],
        "mapping": parsed["mapping"],
        "export_at": parsed["export_at"],
        "source_file": filename,
        "row_count": len(parsed["products"]),
        "wrote_product_master": False,
    }


def _resolve_mapping(headers: List[str], override: Optional[Dict[str, str]]) -> Dict[int, str]:
    mapping: Dict[int, str] = {}
    used = set()
    for index, header in enumerate(headers):
        key = _norm_header(header)
        field = _HEADER_MAP.get(key)
        if field and field not in used:
            mapping[index] = field
            used.add(field)
    if override:
        reverse = {_norm_header(header): index for index, header in enumerate(headers)}
        for header, field in override.items():
            index = reverse.get(_norm_header(header))
            if index is None or not field:
                continue
            mapping[index] = str(field)
    return mapping


def _norm_header(header: str) -> str:
    return str(header or "").strip().lower().replace(" ", "")


def _row_dict(headers: List[str], raw: Tuple[Any, ...], mapping: Dict[int, str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for index, field in mapping.items():
        if index < len(raw):
            out[field] = raw[index]
    return out


def _site_currency(country: Any, shop: Any) -> Tuple[str, Optional[str]]:
    country_text = str(country or "").strip()
    shop_text = str(shop or "").strip()
    upper = f"{country_text} {shop_text}".upper()
    if "美国" in country_text or country_text.upper() in {"US", "USA"} or shop_text.upper().endswith("-US") or "UNITED STATES" in upper:
        return "US", "USD"
    if "加拿大" in country_text or country_text.upper() in {"CA", "CAN"} or shop_text.upper().endswith("-CA"):
        return "CA", "CAD"
    return country_text, None


def _product(record: Dict[str, Any], site: str, currency: str) -> Dict[str, Any]:
    price = _num(record.get("price"))
    if price is None:
        price = _num(record.get("sale_price"))
    if price is None:
        price = _num(record.get("total_price"))
    regular = _num(record.get("strike_price"))
    if regular is None:
        regular = _num(record.get("list_price"))
    product: Dict[str, Any] = {
        "sku": str(record.get("msku") or "").strip(),
        "fnsku": str(record.get("fnsku") or "").strip(),
        "asin": str(record.get("asin") or "").strip(),
        "parent_asin": str(record.get("parent_asin") or "").strip(),
        "listing_status": str(record.get("status") or "").strip(),
        "fulfillment_channel": str(record.get("fulfillment") or "").strip(),
        "local_name": str(record.get("local_name") or "").strip(),
        "local_sku": str(record.get("local_sku") or "").strip(),
        "listing_price": price,
        "listing_price_currency": currency,
        "listing_price_basis": "price",
        "listing_price_site": site,
        "regular_price": regular,
        "fee_fba_est": _num(record.get("fee_fba")),
        "fee_referral_rate": _rate(record.get("referral_rate")),
        "data_source": "lingxing",
    }
    from fba_tool.policy import map_category_name

    category = map_category_name(record.get("category_name")) or map_category_name(record.get("big_category"))
    if category:
        product["category"] = category
    return {key: value for key, value in product.items() if value not in (None, "")}


def _purchase_cost(record: Dict[str, Any], product: Dict[str, Any]) -> str:
    if record.get("purchase_cost") in (None, ""):
        return ""
    cost_currency = str(record.get("cost_currency") or "CNY").strip().upper()
    if cost_currency not in {"CNY", "RMB", "¥"}:
        return f"采购成本币种是 {cost_currency or '空'}，不是人民币，未写入"
    amount = _num(record.get("purchase_cost"))
    if amount is None:
        return "采购成本不是数字，未写入"
    product["product_cost_cny"] = amount
    product["product_cost_currency"] = "CNY"
    return ""


def _num(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    try:
        number = float(text)
    except ValueError:
        return None
    if number != number or number in (float("inf"), float("-inf")) or number < 0:
        return None
    return number


def _rate(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    text = str(value).strip().replace(",", "")
    percent = text.endswith("%")
    number = _num(text)
    if number is None:
        return None
    if percent or number > 1:
        return number / 100
    return number
