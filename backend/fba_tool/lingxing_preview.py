"""领星 Listing → 主表预览差异与字段级确认写入。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from fba_tool.master_db import (
    get_latest_lingxing_sync_run,
    get_lingxing_sync_run,
    get_product_by_sku,
    get_products_by_skus,
    list_lingxing_preview_fields,
    list_lingxing_preview_skus,
    list_lingxing_shops,
    list_skus_for_asin,
    mark_lingxing_sync_run_status,
    replace_lingxing_preview,
    sku_conflicts_for,
    upsert_product,
)
from fba_tool.sku_keys import SkuCaseConflict, case_conflicts, sku_key

AMAZON_IDENTITY_FIELDS = (
    "asin",
    "fnsku",
    "parent_asin",
    "sid",
    "listing_status",
    "fulfillment_channel",
)
CUSTOMS_SENSITIVE_FIELDS = ("english_name", "brand")
PRICE_FIELDS = ("listing_price", "regular_price")  # v8 E1 实时售价；S9-step2-fix A1：常规价单独变化也要能写入（D-12 判断促销）
NAME_FIELDS = ("local_name",)  # 领星本地品名
CONFIRM_FIELDS = AMAZON_IDENTITY_FIELDS + CUSTOMS_SENSITIVE_FIELDS + PRICE_FIELDS + NAME_FIELDS

FIELD_LABELS = {
    "listing_price": "实时售价(申报价)",
    "regular_price": "领星常规价（判断促销）",
    "local_name": "领星品名",
    "asin": "ASIN",
    "fnsku": "FNSKU",
    "parent_asin": "父 ASIN",
    "sid": "店铺 ID",
    "listing_status": "上架状态",
    "fulfillment_channel": "配送渠道",
    "english_name": "英文品名（报关）",
    "brand": "品牌（报关）",
}

CONFIRMABLE_STATUSES = {"preview_pending", "partial", "auto_applied", "auto_applied_partial"}  # S5：定时同步自动写入后，剩下“待人工确认”的仍可在预览里确认


class LingxingPreviewError(Exception):
    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _has_value(field: str, value: Any) -> bool:
    if value is None:
        return False
    if field in PRICE_FIELDS:
        return _num_or_none(value) is not None  # A3：无效价格（abc、NaN、inf、≤0）不算有值，不进可写字段
    if field == "sid":
        try:
            return int(float(value)) > 0
        except (TypeError, ValueError):
            return False
    return str(value).strip() not in ("", "None", "null")


def _norm(field: str, value: Any) -> str:
    if not _has_value(field, value):
        return ""
    if field == "sid":
        return str(int(float(value)))
    if field in PRICE_FIELDS:
        num = _num_or_none(value)
        return "" if num is None else f"{num:.2f}"
    text = str(value).strip()
    if field in ("asin", "fnsku", "parent_asin"):
        return text.upper()
    if field == "listing_status":
        return text.lower()
    return text


def _default_checked(
    field: str,
    *,
    is_new: bool,
    mismatch: bool,
    changed: bool,
    local_val: Any,
) -> bool:
    if mismatch:
        return False
    local_has = _has_value(field, local_val)
    if field in CUSTOMS_SENSITIVE_FIELDS:
        return (not local_has) and changed
    if is_new:
        return True
    return changed


def _display(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _as_sid(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        sid = int(float(value))
    except (TypeError, ValueError):
        return None
    return sid if sid > 0 else None


def _shop_marketplace_score(shop: Optional[Dict[str, Any]]) -> int:
    """本工具发美线 FBA：同 MSKU 多店时优先美国站。"""
    if not shop:
        return 0
    cc = str(shop.get("country_code") or "").strip().upper()
    country = str(shop.get("country") or "").strip()
    name = str(shop.get("name") or "").strip().upper()
    if cc in {"US", "USA"} or country in {"美国", "United States"} or name.endswith("-US"):
        return 100
    if cc in {"CA", "CAN"} or country in {"加拿大", "Canada"} or name.endswith("-CA"):
        return 40
    return 20 if cc else 0


def _listing_prefer_score(
    rec: Dict[str, Any],
    shops: Dict[int, Dict[str, Any]],
    master_sid: Optional[int],
) -> int:
    sid = _as_sid(rec.get("sid"))
    shop = shops.get(sid) if sid is not None else None
    score = _shop_marketplace_score(shop)
    if master_sid is not None and sid == master_sid:
        score += 50
    if _has_value("fnsku", rec.get("fnsku")):
        score += 5
    if _has_value("asin", rec.get("asin")):
        score += 3
    channel = str(rec.get("fulfillment_channel") or "").upper()
    if "AMAZON" in channel or channel in {"FBA", "AFN"}:
        score += 2
    return score


def dedupe_listing_products(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """主表以 MSKU 为主键：美加同 SKU 只留一行，避免预览 UNIQUE 冲突。"""
    shops: Dict[int, Dict[str, Any]] = {}
    try:
        for row in list_lingxing_shops():
            sid = _as_sid(row.get("sid"))
            if sid is not None:
                shops[sid] = row
    except Exception:  # noqa: BLE001
        shops = {}
    sku_keys = [str(p.get("sku") or "").strip() for p in products if str(p.get("sku") or "").strip()]
    master_map = get_products_by_skus(sku_keys) if sku_keys else {}
    chosen: Dict[str, Dict[str, Any]] = {}
    for rec in products:
        sku = str(rec.get("sku") or "").strip()
        if not sku:
            continue
        existing = chosen.get(sku)
        if existing is None:
            chosen[sku] = rec
            continue
        master_sid = _as_sid((master_map.get(sku) or {}).get("sid"))
        if _listing_prefer_score(rec, shops, master_sid) > _listing_prefer_score(existing, shops, master_sid):
            chosen[sku] = rec
    return list(chosen.values())


def build_listing_preview(
    run_id: int, products: List[Dict[str, Any]], history_hints: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """根据 Listing 映射结果生成预览行，不写 product_master。"""
    products = dedupe_listing_products(products)
    sku_keys = [str(p.get("sku") or "").strip() for p in products if str(p.get("sku") or "").strip()]
    master_map = get_products_by_skus(sku_keys)
    # S9-step3：只差大小写的 SKU——领星本批内有多个写法，或本地库里有多个写法又没有原样相同的——不自动合并，放“待人工确认”
    batch_conf = {k: v for k, v in case_conflicts(sku_keys).items()}
    local_conf = sku_conflicts_for(sku_keys)
    sku_rows: List[Dict[str, Any]] = []
    field_rows: List[Dict[str, Any]] = []
    summary = {"new": 0, "changed": 0, "sku_mismatch": 0, "unchanged": 0, "default_checked_fields": 0}

    for rec in products:
        sku = str(rec.get("sku") or "").strip()
        if not sku:
            continue
        existing = master_map.get(sku) or get_product_by_sku(sku)
        is_new = existing is None
        asin = str(rec.get("asin") or "").strip()
        others: List[str] = []
        if asin:
            others = [s for s in list_skus_for_asin(asin) if sku_key(s) != sku_key(sku)]
        conflict = sorted(set(batch_conf.get(sku_key(sku), [])) | set(local_conf.get(sku, [])))
        if conflict:
            rec = dict(rec, _case_conflict=conflict)
        mismatch = bool(is_new and others and not conflict)

        needs_review = bool(conflict) or bool(is_new and not mismatch and review_reasons(rec))
        changed_any = False
        sku_fields: List[Dict[str, Any]] = []
        local_sources = (existing or {}).get("field_sources") or {}
        for field in CONFIRM_FIELDS:
            remote_val = rec.get(field)
            if not _has_value(field, remote_val):
                continue
            local_val = None if is_new else (existing or {}).get(field)
            changed = _norm(field, remote_val) != _norm(field, local_val)
            if changed:
                changed_any = True
            checked = _default_checked(
                field,
                is_new=is_new,
                mismatch=mismatch,
                changed=changed,
                local_val=local_val,
            )
            if local_sources.get(field) == "manual" and field not in PRICE_FIELDS:
                checked = False  # 手填锁定：默认不勾，确认时也会跳过
            if needs_review:
                checked = False  # S8 D10：待人工确认的新品默认不勾，定时自动写入也不会写
            sku_fields.append(
                {
                    "sku": sku,
                    "field": field,
                    "local_value": _display(local_val),
                    "remote_value": _display(remote_val),
                    "default_checked": checked,
                }
            )
            if checked:
                summary["default_checked_fields"] += 1

        if mismatch:
            group = "sku_mismatch"
        elif needs_review:
            group = "needs_review"
        elif is_new:
            group = "new"
        elif changed_any:
            group = "changed"
        else:
            group = "unchanged"
        summary[group] = summary.get(group, 0) + 1

        if history_hints is not None:
            # S9-step4（D-15）：按默认勾选模拟确认后的状态，和预览面板同一个结果
            try:
                if preview_price_info(rec, existing, sku_fields).get("history_hint"):
                    history_hints.append(sku)
            except Exception:  # noqa: BLE001  提示失败不影响同步
                pass
        sku_rows.append(
            {
                "sku": sku,
                "is_new": is_new,
                "group_kind": group,
                "mismatch_skus": ",".join(others),
                "remote_json": json.dumps(rec, ensure_ascii=False, default=str),
            }
        )
        if group != "unchanged":
            field_rows.extend(sku_fields)

    replace_lingxing_preview(run_id, sku_rows, field_rows)
    return summary


_MOJIBAKE = ("锟斤拷", "\ufffd", "Ã", "Â", "é锟", "烫烫", "屯屯")


def review_reasons(rec: Dict[str, Any]) -> List[str]:
    """S8 D10：新品里这几种情况要人工确认，默认不勾：SKU 像乱码、缺 FNSKU、缺 ASIN。"""
    reasons: List[str] = []
    sku = str(rec.get("sku") or "")
    if any(m in sku for m in _MOJIBAKE) or any(ord(ch) < 32 for ch in sku):
        reasons.append("SKU 像乱码")
    elif any(ord(ch) > 127 for ch in sku) and not any("\u4e00" <= ch <= "\u9fff" for ch in sku):
        reasons.append("SKU 含异常字符（可能是乱码）")
    if not str(rec.get("fnsku") or "").strip():
        reasons.append("缺 FNSKU")
    if not str(rec.get("asin") or "").strip():
        reasons.append("缺 ASIN")
    conflict = rec.get("_case_conflict") or []
    if conflict:
        reasons.append("SKU 只差大小写的有多个：" + "、".join(str(c) for c in conflict) + "，不自动合并")
    return reasons


def _drop_pct(listing_price: Any, normal: Any):
    from decimal import Decimal

    try:
        lp, n = Decimal(str(listing_price)), Decimal(str(normal))
        if n <= 0:
            return None
        return (n - lp) / n * 100
    except Exception:  # noqa: BLE001
        return None


def promo_drop_text(listing_price: Any, normal: Any) -> str:
    """S9-step3 UI(j)：降幅统一 1 位小数（向下取，不会把没到的显示成到了）；“低”和数字之间有空格。
    实际超过 5%、向下取后显示 5.0% 时写“低约 5.0%（已超过 5% 阈值）”。"""
    from decimal import ROUND_FLOOR, Decimal

    pct = _drop_pct(listing_price, normal)
    if pct is None:
        return ""
    v = pct.quantize(Decimal("0.1"), rounding=ROUND_FLOOR)
    if pct > 5 and v <= 5:
        return "低约 5.0%（已超过 5% 阈值）"
    return f"低 {v}%"


def regular_gap_text(listing_price: Any, regular: Any) -> str:
    """S9-step3 UI(i)：领星常规价高于售价、但售价低不到 5%（不算促销）时的说明。"""
    from decimal import ROUND_FLOOR, Decimal

    pct = _drop_pct(listing_price, regular)
    if pct is None or pct <= 0 or pct > 5:
        return ""
    v = pct.quantize(Decimal("0.1"), rounding=ROUND_FLOOR)
    return f"售价只比领星常规价低 {v}%，未超过 5% 促销阈值，不算促销"


PRICE_SOURCE_LABELS = {
    "lingxing": "售价",
    "lingxing_regular": "正常价 · 领星常规价",  # S9-step3 UI(h)：不再括号套括号
    "lingxing_recent_nonpromo": "正常价 · 近 90 天非促销价",
    "manual": "手填申报价",
    "lingxing_price": "领星 price 兜底",
    "lingxing_landed_price": "领星 landed_price 兜底",
    "legacy": "旧申报价",
}


def _num_or_none(v: Any) -> Optional[float]:
    """A3：价格统一解析。"1,299.00"、"$12" 能解析；"abc"、NaN、inf、负数、0、空值都返回 None，不抛异常。"""
    if v is None or isinstance(v, bool):
        return None
    from fba_tool.lingxing_adapter import parse_price

    try:
        return parse_price(v)
    except Exception:  # noqa: BLE001  任何异常输入都视为无效，不让预览接口 500
        return None


def _price_key(fields: Iterable[str]) -> str:
    """勾选组合的键：按 PRICE_FIELDS 固定顺序，用 + 连接；都没勾 = ""。"""
    chosen = set(fields)
    return "+".join(f for f in PRICE_FIELDS if f in chosen)


def _price_combos(offered: List[str]) -> List[List[str]]:
    combos: List[List[str]] = [[]]
    for f in PRICE_FIELDS:
        if f in offered:
            combos = combos + [c + [f] for c in combos]
    return combos


def _simulate_price(remote: Dict[str, Any], existing: Optional[Dict[str, Any]], write: Iterable[str]) -> Dict[str, Any]:
    """按“实际会写入的价格字段”模拟确认后的产品，再走 resolve_declared_price（与写库、报关包同一套规则）。"""
    from fba_tool.product_fields import (
        _now,
        _recent_regular,
        _track_nonpromo,
        normal_price,
        price_history_hint,
        promo_info,
        regular_price_in_window,
        resolve_declared_price,
    )

    write = set(write)
    base: Dict[str, Any] = dict(existing or {})
    sim: Dict[str, Any] = dict(base)
    warnings: List[str] = []
    r_lp = _num_or_none(remote.get("listing_price"))
    r_rp = _num_or_none(remote.get("regular_price"))
    issue_fields = set()
    for iss in remote.get("price_issues") or []:  # N3：同步时记下的原始值和原因
        if isinstance(iss, dict) and iss.get("message"):
            if str(iss["message"]) not in warnings:  # S9-step3 #3：同一个坏值只提示一次
                warnings.append(str(iss["message"]))
            issue_fields.add(iss.get("field"))
    for key, raw, num in (("listing_price", remote.get("listing_price"), r_lp),
                          ("regular_price", remote.get("regular_price"), r_rp)):
        if raw not in (None, "") and num is None and key not in issue_fields:
            warnings.append(("领星售价" if key == "listing_price" else "领星常规价") + f"“{str(raw)[:20]}”无效，未写入，保留原值")
    sets: Dict[str, Any] = {}
    if "listing_price" in write and r_lp is not None:
        sets["listing_price"] = r_lp
        if remote.get("listing_price_currency"):
            sets["listing_price_currency"] = remote["listing_price_currency"]
        sets["listing_price_basis"] = remote.get("listing_price_basis") or "listing_price"
    if "regular_price" in write and r_rp is not None:
        sets["regular_price"] = r_rp
        sets["regular_price_at"] = _now()  # 与 set_product_fields 一致：本次写入的常规价，采集时间就是现在（D-16）
    if "listing_price" in sets:
        _track_nonpromo(sets, base)  # 与 set_product_fields 一致：写售价时更新“最近非促销价”
    sim.update(sets)
    for key in ("listing_price", "regular_price"):
        if key in sim and sim.get(key) not in (None, "") and _num_or_none(sim.get(key)) is None:
            sim[key] = None  # 本地旧值异常（0、NaN 等）不参与计算
    lp = _num_or_none(sim.get("listing_price"))
    rp = _num_or_none(sim.get("regular_price"))
    try:
        declared, src = resolve_declared_price(sim)
        declared = _num_or_none(declared)
    except Exception:  # noqa: BLE001
        declared, src = None, ""
    if declared is None:
        src = ""
        warnings.append("没有有效的申报价（售价为空、为 0 或无效），请检查后再导出报关")
    promo = None
    try:
        promo = promo_info(sim)
    except Exception:  # noqa: BLE001
        promo = None
    normal, normal_src = (None, "")
    try:
        normal, normal_src = normal_price(sim)
    except Exception:  # noqa: BLE001
        pass

    def origin(key: str, remote_num: Optional[float]) -> str:
        if key in sets:
            return "remote"
        return "local" if _num_or_none(sim.get(key)) is not None else ""

    currency = str(sim.get("listing_price_currency") or "").strip().upper()
    return {
        "currency": currency,
        "listing_price": lp,
        "listing_price_origin": origin("listing_price", r_lp),
        "regular_price": rp,
        "regular_price_origin": origin("regular_price", r_rp),
        # S9-step4（D-16）：有信息 = 高于售价且在采集后 90 天内
        "regular_price_informative": _recent_regular(sim, lp) is not None,
        "regular_price_at": (str(sim.get("regular_price_at") or "")[:10] if rp is not None else ""),
        "regular_price_expired": bool(rp is not None and not regular_price_in_window(sim)),
        "declared_price": round(declared, 2) if declared is not None else None,
        "declared_source": src,
        "declared_source_label": PRICE_SOURCE_LABELS.get(src, src or ""),
        "promo": bool(promo),
        "declared_above_listing": bool(declared is not None and lp is not None and declared > lp + 1e-9),
        "promo_drop_pct": (promo or {}).get("drop_pct"),
        "promo_drop_text": promo_drop_text(promo["listing_price"], promo["normal_price"]) if promo else "",
        "regular_gap_text": (regular_gap_text(lp, rp) if (not promo and lp is not None
                                                          and _recent_regular(sim, lp) is not None) else ""),
        # S9-step4（D-15）：S9-B 提示（琥珀色）。只提示，不改申报价；不建议 list_price
        "history_hint": price_history_hint(sim) if declared is not None else "",
        "normal_price": round(float(normal), 2) if normal is not None else None,
        "normal_source_label": PRICE_SOURCE_LABELS.get(normal_src, normal_src or ""),
        "normal_basis_label": {"lingxing_regular": "领星常规价", "lingxing_recent_nonpromo": "近 90 天非促销价"}.get(normal_src, ""),
        "warnings": warnings,
    }


def preview_price_info(
    remote: Dict[str, Any],
    existing: Optional[Dict[str, Any]],
    fields: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """S9-step2 A / S9-step2-fix A1–A3、U1：预览里的价格信息。

    - 按“实际会写入的字段”计算：默认结果 = 默认勾选的价格字段；variants 给出每种勾选组合的结果，
      前端按当前勾选取对应一项（取消勾选售价或常规价时联动）。
    - fields=None 表示“领星给了的价格字段都会写”（旧调用方式）。
    - regular_price_origin：remote = 本次领星返回并写入；local = 库里的旧值；"" = 没有。
    只读计算，不写库；规则全部复用 product_fields（D-12 / D-13 不变，list_price 不参与）。
    """
    if fields is None:
        offered = [f for f in PRICE_FIELDS if _has_value(f, remote.get(f))]
        default = list(offered)
    else:
        offered = [f["field"] for f in fields if f.get("field") in PRICE_FIELDS]
        default = [f["field"] for f in fields if f.get("field") in PRICE_FIELDS and f.get("default_checked")]
    variants = {_price_key(c): _simulate_price(remote, existing, c) for c in _price_combos(offered)}
    info = dict(variants[_price_key(default)])
    info["price_fields"] = [f for f in PRICE_FIELDS if f in offered]
    info["default_key"] = _price_key(default)
    info["variants"] = variants
    return info


def serialize_preview(run_id: int) -> Dict[str, Any]:
    run = get_lingxing_sync_run(run_id)
    sku_rows = list_lingxing_preview_skus(run_id)
    field_rows = list_lingxing_preview_fields(run_id)
    by_sku: Dict[str, List[Dict[str, Any]]] = {}
    masters = get_products_by_skus(sorted({row["sku"] for row in field_rows}))
    for row in field_rows:
        msrc = (masters.get(row["sku"]) or {}).get("field_sources") or {}
        # 价格字段不受手填锁定（NEVER_LOCKED_FOR_LINGXING），这里也不显示锁定
        item = {
            "field": row["field"],
            "label": FIELD_LABELS.get(row["field"], row["field"]),
            "local_value": row["local_value"],
            "remote_value": row["remote_value"],
            "default_checked": row["default_checked"],
            "sensitive": row["field"] in CUSTOMS_SENSITIVE_FIELDS,
            "locked": msrc.get(row["field"]) == "manual" and row["field"] not in PRICE_FIELDS,
        }
        by_sku.setdefault(row["sku"], []).append(item)

    all_masters = get_products_by_skus(sorted({row["sku"] for row in sku_rows}))
    groups: Dict[str, List[Dict[str, Any]]] = {
        "new": [],
        "needs_review": [],
        "changed": [],
        "sku_mismatch": [],
        "unchanged": [],
    }
    for row in sku_rows:
        sku = row["sku"]
        kind = row["group_kind"] or "unchanged"
        if kind not in groups:
            groups[kind] = []
        mismatch = [s for s in str(row.get("mismatch_skus") or "").split(",") if s]
        try:
            remote = json.loads(row.get("remote_json") or "{}")
        except (TypeError, ValueError):
            remote = {}
        if not isinstance(remote, dict):
            remote = {}
        sku_fields = by_sku.get(sku, [])
        groups[kind].append(
            {
                "sku": sku,
                "is_new": bool(row.get("is_new")),
                "group_kind": kind,
                "mismatch_skus": mismatch,
                "review_reasons": review_reasons(remote) if kind == "needs_review" else [],
                "fields": sku_fields,
                "price_info": preview_price_info(remote, all_masters.get(sku), sku_fields),
            }
        )
    summary = {key: len(val) for key, val in groups.items()}
    return {
        "run_id": run_id,
        "status": (run or {}).get("status") or "",
        "groups": groups,
        "summary": summary,
        "field_labels": FIELD_LABELS,
    }


def apply_lingxing_field_patch(sku: str, fields: Iterable[str], remote: Dict[str, Any]) -> Dict[str, List[str]]:
    """只写勾选字段；其余列保持库内原值。禁止整行 Listing upsert。

    手填（manual）字段锁定：跳过不写（与领星文件导入同一规则）；写入的字段来源记为 lingxing。
    价格字段（售价、常规价）各自按勾选写入（S9-step2-fix A1：常规价单独变化也写）；无效价格不写，记 skipped_invalid。
    返回 {written, skipped_locked, skipped_invalid}。
    """
    from fba_tool.product_fields import OWN_FIELDS, SOURCE_LINGXING, SOURCE_MANUAL, mark_field_sources, set_product_fields

    key = str(sku or "").strip()
    allowed = [f for f in fields if f in CONFIRM_FIELDS]
    result: Dict[str, List[str]] = {"written": [], "skipped_locked": [], "skipped_invalid": []}
    if not key or not allowed:
        return result
    existing = get_product_by_sku(key)
    sources = (existing or {}).get("field_sources") or {}
    rec: Dict[str, Any] = dict(existing) if existing else {"sku": key}
    rec["sku"] = key
    own_vals: Dict[str, Any] = {}
    plain: List[str] = []
    for field in allowed:
        if sources.get(field) == SOURCE_MANUAL and field not in PRICE_FIELDS:
            result["skipped_locked"].append(field)
            continue
        if field in PRICE_FIELDS:
            num = _num_or_none(remote.get(field))
            if num is None:
                result["skipped_invalid"].append(field)  # A3：售价/常规价无效（0、NaN、abc…）不写，保留原值
            else:
                own_vals[field] = num
            continue
        if field in OWN_FIELDS:
            if remote.get(field) not in (None, ""):
                own_vals[field] = remote.get(field)
            continue
        rec[field] = remote.get(field)
        plain.append(field)
    rec["lingxing_synced_at"] = remote.get("lingxing_synced_at") or datetime.now(timezone.utc).isoformat()
    rec["data_source"] = "lingxing"
    upsert_product(rec, overwrite=True)
    if plain:
        mark_field_sources(key, plain, SOURCE_LINGXING)
        result["written"].extend(plain)
    if own_vals:
        if "listing_price" in own_vals:
            if remote.get("listing_price_currency"):
                own_vals["listing_price_currency"] = remote["listing_price_currency"]
            own_vals["listing_price_basis"] = remote.get("listing_price_basis") or "listing_price"
        res = set_product_fields(key, own_vals, SOURCE_LINGXING)
        result["skipped_locked"].extend(f for f in res["skipped_locked"] if f not in result["skipped_locked"])
        result["written"].extend(
            f for f in own_vals if f not in res["skipped_locked"] and f not in ("listing_price_currency", "listing_price_basis")
        )
    return result


def confirm_lingxing_preview(run_id: int, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    run = get_lingxing_sync_run(int(run_id))
    if not run:
        raise LingxingPreviewError("找不到该次拉取记录", 404)
    latest = get_latest_lingxing_sync_run()
    if not latest or int(latest["id"]) != int(run_id):
        raise LingxingPreviewError("已有更新的拉取结果，请重新同步后再确认", 409)
    status = str(run.get("status") or "")
    if status == "confirmed":
        raise LingxingPreviewError("该次预览已确认写入，请重新同步", 409)
    if status not in CONFIRMABLE_STATUSES:
        raise LingxingPreviewError(f"当前状态不可确认写入：{status or '未知'}", 409)

    sku_map = {row["sku"]: row for row in list_lingxing_preview_skus(int(run_id))}
    patched = 0
    field_count = 0
    skipped = 0
    locked = 0
    for item in items or []:
        sku = str(item.get("sku") or "").strip()
        fields = [str(f).strip() for f in (item.get("fields") or []) if str(f).strip() in CONFIRM_FIELDS]
        if not sku or not fields:
            skipped += 1
            continue
        row = sku_map.get(sku)
        if not row:
            skipped += 1
            continue
        try:
            remote = json.loads(row.get("remote_json") or "{}")
        except json.JSONDecodeError:
            skipped += 1
            continue
        if not isinstance(remote, dict):
            skipped += 1
            continue
        try:
            res = apply_lingxing_field_patch(sku, fields, remote)
        except SkuCaseConflict:  # S9-step3：只差大小写的多条，不任选一条写
            skipped += 1
            continue
        patched += 1
        field_count += len(res["written"])
        locked += len(res["skipped_locked"])

    mark_lingxing_sync_run_status(int(run_id), "confirmed")
    return {
        "ok": True,
        "run_id": int(run_id),
        "skus_patched": patched,
        "fields_written": field_count,
        "skipped": skipped,
        "locked_skipped": locked,
    }


def latest_preview_payload() -> Optional[Dict[str, Any]]:
    run = get_latest_lingxing_sync_run()
    if not run:
        return None
    status = str(run.get("status") or "")
    if status not in CONFIRMABLE_STATUSES and status != "confirmed":
        return None
    payload = serialize_preview(int(run["id"]))
    payload["pending"] = status in CONFIRMABLE_STATUSES
    return payload
