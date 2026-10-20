"""领星 MCP → 本地 SQLite 串行同步编排。

身份字段（asin/fnsku/英文名等）可覆盖；箱规/报关/单品尺寸不写入，避免覆盖手填值。
Listing 失败中止；库存/补货/表现失败记入同步差异后继续。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

from fba_tool.app_paths import resolve_config_read, resolve_config_write
from fba_tool.lingxing_mcp_client import (
    DEFAULT_MCP_URL,
    LingxingMcpClient,
    LingxingMcpError,
    pick_field,
)
from fba_tool.lingxing_preview import build_listing_preview
from fba_tool.sku_keys import case_conflicts, sku_key
from fba_tool.master_db import (
    add_lingxing_sync_diff,
    create_lingxing_sync_run,
    finish_lingxing_sync_run,
    init_master_db,
    list_lingxing_sync_diffs,
    list_sku_case_conflicts,
    list_skus_for_asin,
    replace_lingxing_asin_perf,
    replace_lingxing_fba_stock,
    replace_lingxing_replenish,
    replace_lingxing_shops,
)

CONFIG_NAME = "lingxing.json"
ProgressFn = Callable[[int, str, str], None]


def _read_config() -> Dict[str, Any]:
    path = resolve_config_read(CONFIG_NAME)
    if Path(path).is_file():
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _write_config(data: Dict[str, Any]) -> None:
    dest = resolve_config_write(CONFIG_NAME)
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_lingxing_settings() -> Dict[str, str]:
    """读取领星设置。密钥以 DPAPI 密文存在 mcp_key_enc；老文件里的明文 mcp_key 读一次后迁移成密文并删掉明文。"""
    import logging

    from fba_tool import secret_store

    data = _read_config()
    url = str(data.get("mcp_url") or DEFAULT_MCP_URL).strip() or DEFAULT_MCP_URL
    key = ""
    enc = str(data.get("mcp_key_enc") or "")
    plain = str(data.get("mcp_key") or "").strip()
    if enc:
        try:
            key = secret_store.unprotect(enc)
        except secret_store.SecretStoreError as exc:
            logging.getLogger(__name__).warning("领星密钥解密失败：%s", exc)
            key = ""
    elif plain:
        key = plain
        if secret_store.available():
            data["mcp_key_enc"] = secret_store.protect(plain)
            data.pop("mcp_key", None)
            _write_config(data)
        else:
            logging.getLogger(__name__).warning("本机不支持 DPAPI，领星密钥仍是明文，请在 Windows 上运行以完成加密迁移")
    return {"mcp_key": key, "mcp_url": url}


def save_lingxing_settings(mcp_key: Optional[str] = None, mcp_url: Optional[str] = None) -> Dict[str, str]:
    """保存时密钥只写密文（mcp_key_enc），文件里不出现明文。"""
    from fba_tool import secret_store

    current = load_lingxing_settings()
    data = _read_config()
    if mcp_key is not None:
        text = str(mcp_key).strip()
        if text:
            data["mcp_key_enc"] = secret_store.protect(text)  # 不可用时抛错，不退回明文
            data.pop("mcp_key", None)
            current["mcp_key"] = text
    if mcp_url is not None:
        url = str(mcp_url).strip() or DEFAULT_MCP_URL
        data["mcp_url"] = url
        current["mcp_url"] = url
    data.pop("mcp_key", None)
    _write_config(data)
    return current


def mask_key(key: str) -> str:
    text = str(key or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "****"
    return f"{text[:4]}****{text[-4:]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _status_label(value: Any) -> str:
    if value in (None, ""):
        return ""
    if value in (1, "1", True, "active", "Active", "ONLINE"):
        return "active"
    if value in (0, "0", False, "inactive", "Inactive"):
        return "inactive"
    return str(value)


def is_amazon_shop(row: Dict[str, Any]) -> bool:
    plat = " ".join(
        [
            _as_str(row.get("platform_name")),
            _as_str(row.get("platform")),
            _as_str(row.get("platformName")),
            _as_str(row.get("source")),
        ]
    ).lower()
    if any(token in plat for token in ("tiktok", "temu", "walmart", "shopify", "shopee", "ebay")):
        return False
    if plat and "amazon" not in plat and plat not in ("amz", "amazon.com"):
        # 未知平台但带了非亚马逊关键词才剔除；空平台默认保留（本账号实测仅 Amazon）
        if "platform" in plat:
            return False
    return True


def listing_to_product(row: Dict[str, Any], synced_at: str) -> Optional[Dict[str, Any]]:
    sku = _as_str(
        pick_field(row, "seller_sku", "msku", "sku", "sellerSku", "local_sku")
    )
    if not sku:
        return None
    from fba_tool.lingxing_adapter import map_listing_row

    mapped = map_listing_row(row)
    extra = {
        k: row.get(k)
        for k in (
            "price",
            "last_star",
            "review_num",
            "review_count",
            "small_rank",
            "small_cate_rank",
            "small_rank_category",
            "small_image_url",
            "currency_code",
            "item_name",
            "local_name",
        )
        if row.get(k) not in (None, "")
    }
    rec = {
        "sku": sku,
        "asin": _as_str(pick_field(row, "asin", "asin_url", "asinUrl")),
        "fnsku": _as_str(pick_field(row, "fnsku", "fnSku", "fulfillment_channel_sku")),
        "english_name": _as_str(pick_field(row, "item_name", "local_name", "title", "product_name", "name")),
        "brand": _as_str(pick_field(row, "brand", "brand_name")),
        "parent_asin": _as_str(pick_field(row, "parent_asin", "parentAsin")),
        "sid": _as_int(pick_field(row, "sid", "s_id")),
        "listing_status": _status_label(pick_field(row, "status", "listing_status")),
        "fulfillment_channel": _as_str(
            pick_field(row, "fulfillment_channel_type", "fulfillment_channel", "fulfillmentChannel")
        ),
        "local_name": _as_str(row.get("local_name")),
        "extra_data": {"lingxing": extra} if extra else None,
        "lingxing_synced_at": synced_at,
        "data_source": "lingxing",
        "listing_price": (mapped or {}).get("listing_price"),
        "listing_price_currency": (mapped or {}).get("listing_price_currency"),
        "listing_price_basis": (mapped or {}).get("listing_price_basis"),
        "regular_price": _price_or_none(row.get("regular_price")),  # D-12：常规价，用来识别促销
    }
    issues = _price_issues(mapped, row)
    if issues:
        rec["price_issues"] = issues
    return rec


def _price_issues(mapped: Optional[Dict[str, Any]], row: Dict[str, Any]) -> List[Dict[str, str]]:
    """S9-step2-fix2 N1–N3：领星给了价格但无效时，记原始值和原因（预览 / 同步差异里提示，不写入）。"""
    from fba_tool.lingxing_adapter import parse_price_reason

    out: List[Dict[str, str]] = []
    seen = set()

    def add(field: str, raw: str, reason: str, label: str) -> None:
        if (field, raw, reason) in seen:  # S9-step3 #3：同一个坏值只提示一次
            return
        seen.add((field, raw, reason))
        out.append({"field": field, "raw": raw, "reason": reason,
                    "message": f"{label}“{raw}”无效：{reason}，未写入，保留原值"})

    for iss in (mapped or {}).get("price_issues") or []:
        add("listing_price", str(iss.get("raw", "")), str(iss.get("reason", "")), "领星售价")
    raw = row.get("regular_price")
    if raw not in (None, ""):
        num, reason = parse_price_reason(raw)
        if num is None and reason:
            add("regular_price", str(raw)[:40], reason, "领星常规价")
    return out


def _price_or_none(v: Any) -> Optional[float]:
    """S9-step2-fix A3：与售价同一解析（千分位、$）；abc、NaN、inf、≤0 返回 None。"""
    from fba_tool.lingxing_adapter import parse_price

    if isinstance(v, bool):
        return None
    try:
        return parse_price(v)
    except Exception:  # noqa: BLE001
        return None


def _amazon_sid(row: Dict[str, Any]) -> Optional[int]:
    """只取领星系统店铺 ID（如 9001），忽略多平台雪花 store_id。"""
    for key in ("sid", "s_id"):
        val = _as_int(row.get(key))
        if val is not None and 0 < val < 10_000_000:
            return val
    val = _as_int(row.get("id"))
    if val is not None and 0 < val < 10_000_000:
        return val
    return None


def shop_to_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sid = _amazon_sid(row)
    if sid is None:
        return None
    extra = {k: v for k, v in row.items() if k not in ("sid", "name", "store_name")}
    return {
        "sid": sid,
        "name": _as_str(pick_field(row, "name", "store_name", "shop_name", "seller_name")),
        "country": _as_str(pick_field(row, "country", "nation", "marketplace", "site_name_cn")),
        "country_code": _as_str(pick_field(row, "country_code", "countryCode", "marketplace_id")),
        "seller_id": _as_str(pick_field(row, "seller_id", "sellerId", "merchant_id", "seller_name")),
        "currency": _as_str(pick_field(row, "currency", "currency_code")),
        "platform_name": _as_str(pick_field(row, "platform_name", "platform", "platformName")) or "Amazon",
        "status": _as_int(pick_field(row, "status", default=1)),
        "extra_json": extra,
    }


def stock_to_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sku = _as_str(pick_field(row, "msku", "seller_sku", "sku"))
    if not sku:
        return None
    extra = json.dumps(row, ensure_ascii=False) if row else None
    return {
        "sku": sku,
        "asin": _as_str(pick_field(row, "asin")),
        "fnsku": _as_str(pick_field(row, "fnsku")),
        "sid": _as_int(pick_field(row, "sid")),
        "seller_name": _as_str(pick_field(row, "seller_name", "name")),
        "fulfillable": _as_float(pick_field(row, "afn_fulfillable_quantity", "fulfillable")),
        "reserved": _as_float(pick_field(row, "reserved_fc_transfers", "reserved")),
        "inbound_shipped": _as_float(pick_field(row, "afn_inbound_shipped_quantity", "inbound_shipped")),
        "inbound_working": _as_float(pick_field(row, "afn_inbound_working_quantity", "inbound_working")),
        "inbound_receiving": _as_float(pick_field(row, "afn_inbound_receiving_quantity", "inbound_receiving")),
        "unfulfillable": _as_float(pick_field(row, "afn_unsellable_quantity", "unfulfillable")),
        "age_0_30": _as_float(pick_field(row, "inv_age_0_to_30_days", "age_0_30")),
        "age_31_60": _as_float(pick_field(row, "inv_age_31_to_60_days", "age_31_60")),
        "age_61_90": _as_float(pick_field(row, "inv_age_61_to_90_days", "age_61_90")),
        "age_91_180": _as_float(pick_field(row, "inv_age_91_to_180_days", "age_91_180")),
        "total_cost": _as_float(pick_field(row, "total_cost")),
        "extra_json": extra,
    }


def replenish_to_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    display = row.get("displayInfo") if isinstance(row.get("displayInfo"), dict) else {}
    suggest = row.get("suggestInfo") if isinstance(row.get("suggestInfo"), dict) else {}
    amazon_qty = row.get("amazonQuantityInfo") if isinstance(row.get("amazonQuantityInfo"), dict) else {}
    sales = row.get("salesInfo") if isinstance(row.get("salesInfo"), dict) else {}
    basic = row.get("basicInfo") if isinstance(row.get("basicInfo"), dict) else {}
    products = display.get("productList") if isinstance(display.get("productList"), list) else []
    relations = basic.get("relationListing") if isinstance(basic.get("relationListing"), list) else []
    asins = display.get("asinList") if isinstance(display.get("asinList"), list) else []

    sku = _as_str(pick_field(row, "msku", "seller_sku", "sku"))
    if not sku and relations and isinstance(relations[0], dict):
        sku = _as_str(pick_field(relations[0], "msku", "sku"))
    if not sku and products and isinstance(products[0], dict):
        sku = _as_str(pick_field(products[0], "sku", "msku"))

    asin = _as_str(pick_field(row, "asin")) or _as_str(display.get("asin"))
    if not asin and asins:
        asin = _as_str(asins[0])
    if not asin and relations and isinstance(relations[0], dict):
        asin = _as_str(relations[0].get("asin"))

    if not sku and not asin:
        return None
    extra = json.dumps(row, ensure_ascii=False)
    sid = _as_int(pick_field(row, "sid", "storeId"))
    if sid is None and relations and isinstance(relations[0], dict):
        sid = _as_int(relations[0].get("storeId") or relations[0].get("sid"))
    return {
        "sku": sku,
        "asin": asin,
        "sid": sid,
        "title": _as_str(pick_field(row, "title", "item_name", "local_name") or display.get("itemName")),
        "days_fba": _as_float(
            pick_field(row, "days_of_supply", "fba_days", "available_days", "days")
            or suggest.get("availableSaleDaysFba")
            or suggest.get("fbaAvailableSaleDays")
        ),
        "qty_purchase": _as_float(
            pick_field(row, "recommended_replenishment_qty", "qty_purchase", "suggest_qty")
            or suggest.get("quantitySugPurchase")
        ),
        "qty_local_to_fba": _as_float(
            pick_field(row, "local_to_fba", "qty_local_to_fba", "ship_qty")
            or suggest.get("quantitySugLocalToFba")
        ),
        "sales_30": _as_float(pick_field(row, "sales_30", "volume", "units_30") or sales.get("salesTotal30")),
        "fulfillable": _as_float(
            pick_field(row, "afn_fulfillable_quantity", "fulfillable")
            or amazon_qty.get("afnFulfillableQuantity")
        ),
        "out_stock_date": _as_str(
            pick_field(row, "estimated_oos_date", "out_stock_date", "oos_date")
            or suggest.get("outStockDate")
        ),
        "extra_json": extra,
    }


def perf_to_row(row: Dict[str, Any], period_start: str, period_end: str) -> Optional[Dict[str, Any]]:
    asin = _as_str(pick_field(row, "asin"))
    if not asin:
        return None
    extra = json.dumps(row, ensure_ascii=False)
    return {
        "asin": asin,
        "title": _as_str(pick_field(row, "item_name", "title", "local_name")),
        "amount": _as_float(pick_field(row, "amount", "sales_amount")),
        "volume": _as_float(pick_field(row, "volume", "sales_volume", "units")),
        "gross_profit": _as_float(pick_field(row, "gross_profit", "profit")),
        "spend": _as_float(pick_field(row, "spend", "ad_spend")),
        "acos": _as_float(pick_field(row, "acos")),
        "return_rate": _as_float(pick_field(row, "return_rate", "refund_rate")),
        "sessions": _as_float(pick_field(row, "sessions", "session")),
        "extra_json": extra,
        "period_start": period_start,
        "period_end": period_end,
    }


def _lerp(start: int, end: int, current: int, total: int) -> int:
    if total <= 0:
        return end
    ratio = min(1.0, max(0.0, current / total))
    return int(start + (end - start) * ratio)


def run_full_sync(
    client: Optional[LingxingMcpClient] = None,
    on_progress: Optional[ProgressFn] = None,
) -> Dict[str, Any]:
    """执行全量同步并返回结果摘要。"""
    events: List[Dict[str, Any]] = []
    result: Dict[str, Any] = {}
    for event in iter_full_sync_events(client=client, on_progress=on_progress):
        events.append(event)
        if event.get("event") == "result":
            result = event.get("data") or {}
        if event.get("event") == "error":
            raise LingxingMcpError(event.get("message") or "领星同步失败")
    return result


def iter_full_sync_events(
    client: Optional[LingxingMcpClient] = None,
    on_progress: Optional[ProgressFn] = None,
) -> Iterator[Dict[str, Any]]:
    init_master_db()
    settings = load_lingxing_settings()
    if not settings["mcp_key"]:
        yield {
            "event": "error",
            "message": "未配置领星 MCP Key，请在侧栏系统设置中填写。",
        }
        return

    run_id = create_lingxing_sync_run()
    steps: List[Dict[str, Any]] = []
    counts: Dict[str, Any] = {}
    diffs: List[Dict[str, str]] = []
    synced_at = _now_iso()
    fatal: Optional[str] = None

    def emit(percent: int, step: str, message: str) -> Dict[str, Any]:
        if on_progress:
            on_progress(percent, step, message)
        return {"event": "progress", "percent": int(percent), "step": step, "message": message}

    def note_step(name: str, ok: bool, detail: str, extra: Optional[Dict[str, Any]] = None) -> None:
        item = {"name": name, "ok": ok, "detail": detail}
        if extra:
            item.update(extra)
        steps.append(item)

    def add_diff(kind: str, sku: str, message: str) -> None:
        diffs.append({"kind": kind, "sku": sku, "message": message})
        add_lingxing_sync_diff(run_id, kind, sku, message)

    own_client = client
    if own_client is None:
        own_client = LingxingMcpClient(settings["mcp_key"], settings["mcp_url"])

    amazon_sids: List[int] = []
    try:
        yield emit(1, "init", "正在连接领星 MCP…")
        own_client.initialize()
        yield emit(3, "init", "领星 MCP 已连接，开始同步店铺")

        # 店铺  → 5%
        shops: List[Dict[str, Any]] = []
        try:
            yield emit(4, "shops", "正在同步店铺档案…")
            try:
                sid_payload = own_client.action("get_my_sids", {})
                for row in _as_rows(sid_payload):
                    mapped = shop_to_row(row)
                    if mapped:
                        shops.append(mapped)
            except LingxingMcpError as exc:
                add_diff("permission", "", f"get_my_sids 失败：{exc}")

            try:
                plat_payload = own_client.action(
                    "get_multi_platform_shop_list",
                    {"platform_code": ["10001"]},
                )
                by_sid = {int(s["sid"]): s for s in shops if s.get("sid") is not None}
                for row in _as_rows(plat_payload):
                    mapped = shop_to_row(row)
                    if not mapped:
                        continue
                    by_sid[int(mapped["sid"])] = mapped
                shops = list(by_sid.values())
            except LingxingMcpError as exc:
                add_diff("permission", "", f"get_multi_platform_shop_list 失败：{exc}")

            amazon_shops = [s for s in shops if is_amazon_shop(s)]
            uniq: Dict[int, Dict[str, Any]] = {}
            for s in amazon_shops:
                sid = int(s["sid"])
                prev = uniq.get(sid) or {}
                uniq[sid] = {**prev, **{k: v for k, v in s.items() if v not in (None, "")}}
            amazon_shops = list(uniq.values())
            skipped = [s for s in shops if not is_amazon_shop(s)]
            for s in skipped:
                add_diff(
                    "skip_platform",
                    str(s.get("sid") or ""),
                    f"非 Amazon 店铺不同步：{s.get('name')} / {s.get('platform_name')}",
                )
            replace_lingxing_shops(amazon_shops)
            amazon_sids = sorted({int(s["sid"]) for s in amazon_shops if s.get("sid") is not None})
            counts["shops"] = len(amazon_shops)
            names = "、".join(str(s.get("name") or s.get("sid")) for s in amazon_shops[:6]) or "无"
            note_step("shops", True, f"{len(amazon_shops)} 家 Amazon 店铺：{names}")
            yield emit(5, "shops", f"已同步店铺 {len(amazon_shops)} 家：{names}")
        except Exception as exc:  # noqa: BLE001
            note_step("shops", False, str(exc))
            add_diff("error", "", f"店铺同步失败：{exc}")
            yield emit(5, "shops", f"店铺同步失败，继续尝试 Listing：{exc}")

        # Listing → 40%（失败中止）
        try:
            yield emit(8, "erp_listing", "正在同步 Listing…")
            listing_params: Dict[str, Any] = {"pvi_ids": ""}
            if amazon_sids:
                listing_params["sids"] = ",".join(str(s) for s in amazon_sids)
            listing_rows: List[Dict[str, Any]] = []
            last_page = 1
            for offset, rows, total in own_client.iter_pages(
                "erp_listing",
                listing_params,
                start_offset=0,
                page_size=50,
            ):
                listing_rows.extend(rows)
                last_page = offset // 50 + 1
                yield emit(
                    _lerp(8, 40, len(listing_rows), total or 1),
                    "erp_listing",
                    f"正在同步 Listing 第 {last_page} 页（{len(listing_rows)}/{total or '?'}）",
                )
            products: List[Dict[str, Any]] = []
            for row in listing_rows:
                try:
                    rec = listing_to_product(row, synced_at)
                except Exception:  # noqa: BLE001  N2：单行解析失败只跳过这一行，整批继续，也不触发重试
                    logging.getLogger(__name__).exception("Listing 行解析失败，已跳过")
                    bad_sku = _as_str(pick_field(row, "seller_sku", "msku", "sku")) if isinstance(row, dict) else ""
                    add_diff("row_skipped", bad_sku, "这一行 Listing 数据无法解析，已跳过，其余照常同步")
                    continue
                if rec is None:
                    add_diff("sku_missing", "", "Listing 行缺少 seller_sku/MSKU，已跳过")
                    continue
                for msg in dict.fromkeys(iss["message"] for iss in rec.get("price_issues") or []):
                    add_diff("price_invalid", rec["sku"], msg)  # S9-step3 #3：同一条只记一次
                asin = rec.get("asin") or ""
                if asin:
                    locals_for_asin = list_skus_for_asin(asin)
                    sku_l = sku_key(rec["sku"])  # S9-step3：大小写 / 全角统一规则
                    others = [s for s in locals_for_asin if sku_key(s) != sku_l]
                    if others and rec["sku"] not in locals_for_asin:
                        add_diff(
                            "sku_mismatch",
                            rec["sku"],
                            f"领星 MSKU={rec['sku']} ASIN={asin} 与本地 SKU={','.join(others)} 不一致，默认不写入，可在预览中勾选",
                        )
                products.append(rec)
            # S9-step3：只差大小写的 SKU 冲突只提示、不自动合并（领星本批内的，以及本地库里的旧数据）
            for grp in case_conflicts(p["sku"] for p in products).values():
                add_diff("sku_case_conflict", grp[0],
                         "领星里有只差大小写/全角半角的多个 MSKU：" + "、".join(grp) + "，没有自动合并，已放到“待人工确认”，请核对")
            for grp in list_sku_case_conflicts():
                add_diff("sku_case_conflict", grp[0],
                         "产品库里有只差大小写/全角半角的多条 SKU：" + "、".join(grp) + "，没有自动合并，请在产品库里确认（改名或删除多余的一条）")
            history_hints: List[str] = []
            preview_summary = build_listing_preview(run_id, products, history_hints)
            from fba_tool.product_fields import HISTORY_HINT_TEXT

            for hsku in history_hints:  # S9-step4（D-15）：S9-B 提示也记进同步差异
                add_diff("price_history_missing", hsku, HISTORY_HINT_TEXT)
            counts["listing_raw"] = len(products)
            counts["listing"] = int(
                preview_summary.get("new", 0)
                + preview_summary.get("changed", 0)
                + preview_summary.get("sku_mismatch", 0)
                + preview_summary.get("unchanged", 0)
            )
            counts["listing_upserted"] = 0
            counts["preview_new"] = int(preview_summary.get("new") or 0)
            counts["preview_changed"] = int(preview_summary.get("changed") or 0)
            counts["preview_mismatch"] = int(preview_summary.get("sku_mismatch") or 0)
            counts["preview_unchanged"] = int(preview_summary.get("unchanged") or 0)
            note_step("erp_listing", True, f"{len(products)} 条 Listing 待确认写入")
            yield emit(
                40,
                "erp_listing",
                f"Listing 已拉取 {len(products)} 条，主表待预览确认（约 {last_page} 页）",
            )
        except Exception as exc:  # noqa: BLE001
            fatal = f"Listing 同步失败，已中止：{exc}"
            note_step("erp_listing", False, str(exc))
            add_diff("error", "", fatal)
            finish_lingxing_sync_run(run_id, "failed", steps, counts, fatal)
            yield {"event": "error", "message": fatal, "fatal": _is_fatal_exc(exc),
                   "error_type": exc.__class__.__name__,
                   "data": _result_payload(run_id, steps, counts, diffs, fatal)}
            return

        # FBA 库存 → 70%
        try:
            yield emit(42, "fba_stock", "正在同步 FBA 库存…")
            stock_params: Dict[str, Any] = {"length": 50}
            if amazon_sids:
                stock_params["sid"] = ",".join(str(s) for s in amazon_sids)
            shop_label = "、".join(str(s) for s in amazon_sids) or "全部"
            raw_stock: List[Dict[str, Any]] = []
            for offset, rows, total in own_client.iter_pages(
                "get_fba_stock_list",
                stock_params,
                start_offset=0,
                page_size=50,
            ):
                raw_stock.extend(rows)
                yield emit(
                    _lerp(42, 70, len(raw_stock), total or 1),
                    "fba_stock",
                    f"正在同步：FBA 库存 {shop_label} {len(raw_stock)}/{total or '?'} 行",
                )
            stock_rows = [r for r in (stock_to_row(x) for x in raw_stock) if r]
            replace_lingxing_fba_stock(stock_rows, synced_at)
            counts["fba_stock"] = len(stock_rows)
            note_step("fba_stock", True, f"{len(stock_rows)} 行")
            yield emit(70, "fba_stock", f"FBA 库存完成：{len(stock_rows)} 行")
        except Exception as exc:  # noqa: BLE001
            note_step("fba_stock", False, str(exc))
            add_diff("error", "", f"FBA 库存同步失败：{exc}")
            yield emit(70, "fba_stock", f"FBA 库存失败，继续补货：{exc}")

        # 补货 → 85%
        try:
            yield emit(72, "replenish", "正在同步补货建议…")
            replenish_params: Dict[str, Any] = {
                "analysisMode": 1,
                "dataType": 1,
                "length": 50,
            }
            if amazon_sids:
                replenish_params["storeIdList"] = amazon_sids

            raw_rep: List[Dict[str, Any]] = []
            for offset, rows, total in own_client.iter_pages(
                "query_fba_valid_list",
                replenish_params,
                start_offset=0,
                page_size=50,
            ):
                raw_rep.extend(rows)
                yield emit(
                    _lerp(72, 85, len(raw_rep), total or 1),
                    "replenish",
                    f"正在同步补货建议第 {offset // 50 + 1} 页（{len(raw_rep)}/{total or '?'}）",
                )
            rep_rows = [r for r in (replenish_to_row(x) for x in raw_rep) if r]
            replace_lingxing_replenish(rep_rows, synced_at)
            counts["replenish"] = len(rep_rows)
            note_step("replenish", True, f"{len(rep_rows)} 行")
            yield emit(85, "replenish", f"补货建议完成：{len(rep_rows)} 行")
        except Exception as exc:  # noqa: BLE001
            note_step("replenish", False, str(exc))
            add_diff("error", "", f"补货建议同步失败：{exc}")
            yield emit(85, "replenish", f"补货建议失败，继续产品表现：{exc}")

        # 产品表现 → 95%
        try:
            end = datetime.now(timezone.utc).date()
            start = end - timedelta(days=29)
            period_start = start.isoformat()
            period_end = end.isoformat()
            yield emit(87, "asin_perf", f"正在同步近 30 天产品表现（{period_start} ~ {period_end}）…")
            perf_params: Dict[str, Any] = {
                "start_date": period_start,
                "end_date": period_end,
                "sort_field": "amount",
                "currency_code": "USD",
                "length": 50,
            }
            if amazon_sids:
                perf_params["sids"] = ",".join(str(s) for s in amazon_sids)

            raw_perf: List[Dict[str, Any]] = []
            for offset, rows, total in own_client.iter_pages(
                "query_product_performance_asin_lists",
                perf_params,
                start_offset=0,
                page_size=50,
            ):
                raw_perf.extend(rows)
                yield emit(
                    _lerp(87, 95, len(raw_perf), total or 1),
                    "asin_perf",
                    f"正在同步产品表现第 {offset // 50 + 1} 页（{len(raw_perf)}/{total or '?'}）",
                )
            perf_rows = [
                r
                for r in (perf_to_row(x, period_start, period_end) for x in raw_perf)
                if r
            ]
            replace_lingxing_asin_perf(perf_rows, synced_at)
            counts["asin_perf"] = len(perf_rows)
            note_step("asin_perf", True, f"{len(perf_rows)} 条 ASIN")
            yield emit(95, "asin_perf", f"产品表现完成：{len(perf_rows)} 条")
        except Exception as exc:  # noqa: BLE001
            note_step("asin_perf", False, str(exc))
            add_diff("error", "", f"产品表现同步失败：{exc}")
            yield emit(95, "asin_perf", f"产品表现失败：{exc}")

        counts["diffs"] = len(diffs)
        listing_ok = any(s.get("name") == "erp_listing" and s.get("ok") for s in steps)
        ok_steps = [s for s in steps if s.get("ok")]
        status = "preview_pending" if listing_ok else "partial"
        if listing_ok and len(ok_steps) != len(steps):
            counts["aux_partial"] = 1
        finish_lingxing_sync_run(run_id, status, steps, counts, None)
        yield emit(100, "done", "库存/补货已更新，产品主表待确认")
        yield {
            "event": "result",
            "percent": 100,
            "data": _result_payload(run_id, steps, counts, diffs, None, status),
        }
    except Exception as exc:  # noqa: BLE001
        fatal = str(exc)
        note_step("fatal", False, fatal)
        finish_lingxing_sync_run(run_id, "failed", steps, counts, fatal)
        yield {"event": "error", "message": fatal, "fatal": _is_fatal_exc(exc), "error_type": exc.__class__.__name__,
               "data": _result_payload(run_id, steps, counts, diffs, fatal)}


def _is_fatal_exc(exc: BaseException) -> bool:
    """S9-step2 M3：按异常类型判断不可恢复（鉴权、只读拒绝、未知工具、定时同步白名单拒绝）。"""
    from fba_tool.lingxing_mcp_client import is_fatal_exception

    if exc.__class__.__name__ == "ReadOnlyViolation":
        return True
    return is_fatal_exception(exc)


def _as_rows(payload: Any) -> List[Dict[str, Any]]:
    from fba_tool.lingxing_mcp_client import extract_list

    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    return extract_list(payload)


def _result_payload(
    run_id: int,
    steps: List[Dict[str, Any]],
    counts: Dict[str, Any],
    diffs: List[Dict[str, str]],
    error: Optional[str],
    status: str = "failed",
) -> Dict[str, Any]:
    stored = list_lingxing_sync_diffs(run_id)
    from fba_tool.lingxing_preview import serialize_preview

    preview = None
    if error is None:
        try:
            preview = serialize_preview(run_id)
            preview["pending"] = status in {"preview_pending", "partial"}
        except Exception:  # noqa: BLE001
            preview = None
    return {
        "ok": error is None,
        "status": status if error is None else "failed",
        "run_id": run_id,
        "steps": steps,
        "counts": {k: v for k, v in counts.items() if not str(k).startswith("_")},
        "diffs": stored or diffs,
        "error": error,
        "preview": preview,
    }
