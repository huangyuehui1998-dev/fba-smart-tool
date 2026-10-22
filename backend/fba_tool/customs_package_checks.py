"""报关金额英文、价格检查、按票装配与一致性校验。从 customs_package 拆出，经它再导出。"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fba_tool.customs_package import (
    DEFAULT_BUYER,
    DEFAULT_UNIT,
    CustomsPackageData,
    _CENT,
    _apply_date_rules,
    _build_remarks,
    _catalog_hints,
    _count_total_boxes,
    _merge_rows,
    _normalize_selected_ids,
    _rows_from_invoice_draft,
    _rule_profile,
    _sku_rows_from_pairs,
    box_tares_for_count,
    compute_net_weight,
    default_dates,
    money_half_up,
    to_dec,
)
from fba_tool.shipment_validator import ShipmentPair

def amount_to_english_words(amount: float) -> str:
    """合同 Total Value in Word；含美分（与 total_amount 数值严格对应）。"""
    ones = [
        "ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE",
        "TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN", "SIXTEEN",
        "SEVENTEEN", "EIGHTEEN", "NINETEEN",
    ]
    tens = ["", "", "TWENTY", "THIRTY", "FORTY", "FIFTY", "SIXTY", "SEVENTY", "EIGHTY", "NINETY"]

    def under_thousand(n: int) -> str:
        if n == 0:
            return ""
        if n < 20:
            return ones[n]
        if n < 100:
            t, r = divmod(n, 10)
            return tens[t] + (f" {ones[r]}" if r else "")
        h, rem = divmod(n, 100)
        rest = under_thousand(rem)
        return ones[h] + " HUNDRED" + (f" {rest}" if rest else "")

    def convert(n: int) -> str:
        if n == 0:
            return "ZERO"
        parts: List[str] = []
        remainder = n
        for label, div in (("MILLION", 1_000_000), ("THOUSAND", 1_000)):
            if remainder >= div:
                chunk, remainder = divmod(remainder, div)
                text = under_thousand(chunk)
                if text:
                    parts.append(f"{text} {label}".strip())
        if remainder:
            parts.append(under_thousand(remainder))
        return " ".join(parts).replace("  ", " ").strip()

    rounded = round(float(amount), 2)
    dollars = int(rounded)
    cents = int(round((rounded - dollars) * 100))
    if cents == 100:
        dollars += 1
        cents = 0

    dollar_words = convert(dollars)
    if cents == 0:
        return f"{dollar_words} US DOLLARS ONLY"
    cent_words = convert(cents)
    return f"{dollar_words} US DOLLARS AND {cent_words} CENTS ONLY"


PRICE_SOURCE_LABELS = {
    "manual": "手填申报价",
    "lingxing": "领星实时售价",
    "lingxing_price": "领星 price（兜底）",
    "lingxing_landed_price": "领星 landed_price（兜底）",
    "lingxing_regular": "领星常规价（促销期按正常价，D-12）",
    "lingxing_recent_nonpromo": "近 90 天非促销售价（促销期按正常价，D-12）",
    "legacy": "旧数据（未经领星核实）",
    "invoice": "发票草稿",
    "none": "无价格",
}
PRICE_DROP_RATIO = 0.2  # 领星价比历史申报价低 20% 以上时提示


def price_checks(raw_rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """返回 (price_sources, warnings, blocking)。"""
    per_sku: Dict[str, Dict[str, Any]] = {}
    for row in raw_rows:
        sku = str(row.get("sku") or row.get("chinese_name") or "").strip()
        if not sku or sku in per_sku:
            continue
        src = str(row.get("price_source") or "")
        per_sku[sku] = {
            "sku": sku,
            "product_sku": str(row.get("product_sku") or "").strip(),
            "fnsku": str(row.get("fnsku") or "").strip(),
            "price": row.get("unit_price") if src != "none" else None,
            "source": src,
            "source_label": PRICE_SOURCE_LABELS.get(src, src),
            "legacy_price": row.get("legacy_price"),
            "manual_price": row.get("manual_price"),
            "promo_price": row.get("promo_price"),
            "raw_price": row.get("raw_price") if src != "none" else None,
        }
    sources = list(per_sku.values())
    warnings: List[Dict[str, Any]] = []
    blocking: List[Dict[str, Any]] = []
    legacy = [s["sku"] for s in sources if s["source"] == "legacy"]
    from fba_tool.invoice_rules import missing_price_label

    missing = [
        missing_price_label(sku=s.get("product_sku") or "", fnsku=s.get("fnsku") or "", fallback=s["sku"])
        for s in sources
        if s["source"] == "none"
    ]
    if legacy:
        warnings.append({
            "code": "price_legacy",
            "skus": legacy,
            "message": "申报价来自旧数据，未经领星核实：" + "、".join(legacy) + "。请导入领星售价或手填申报价后再导出。",
        })
    if missing:
        msg = "以下 SKU 没有申报价，不能导出：" + "、".join(missing) + "。请在产品库导入领星售价或手填申报价。"
        warnings.append({"code": "price_missing", "skus": missing, "message": msg})
        blocking.append({"code": "price_missing", "skus": missing, "message": msg})
    unused = []
    for s in sources:
        mp = s.get("manual_price")
        if mp in (None, "") or s["source"] == "manual" or s["source"] == "none":
            continue
        try:
            raw = s.get("raw_price") if s.get("raw_price") is not None else s["price"]
            if abs(float(mp) - float(raw)) < 1e-6:
                continue  # s2-final：手填价与采用价相等，不算“未采用”
            unused.append(f"{s['sku']}（手填 {float(mp):.2f} 未采用，按{PRICE_SOURCE_LABELS.get(s['source'], s['source'])} {float(s['price']):.2f}）")
        except (TypeError, ValueError):
            continue
    if unused:
        warnings.append({
            "code": "manual_price_not_used",
            "skus": [u.split("（")[0] for u in unused],
            "message": "手填申报价未采用（按用户决定，领星实时售价优先）：" + "；".join(unused),
        })
    promos = []
    for s in sources:
        pp = s.get("promo_price")
        if pp in (None, "") or s.get("price") in (None, "") or not str(s.get("source") or "").startswith("lingxing"):
            continue
        promos.append(f"{s['sku']}（实时售价 {float(pp):.2f} 是促销价，按{PRICE_SOURCE_LABELS.get(s['source'], s['source'])} {float(s['price']):.2f} 申报）")
    if promos:
        warnings.append({
            "code": "promo_price_not_used",
            "skus": [x.split("（")[0] for x in promos],
            "message": "领星实时售价低于正常价 5% 以上（促销），按用户决定 D-12 改按正常价申报，请确认：" + "；".join(promos),
        })
    drops = []
    for s in sources:
        try:
            raw = s.get("raw_price") if s.get("raw_price") is not None else s.get("price")
            old_d, new_d = Decimal(str(s.get("legacy_price") or 0)), Decimal(str(raw or 0))
            old, new = float(old_d), float(new_d)
        except (TypeError, ValueError, ArithmeticError):
            continue
        # s2-final：用原值（Decimal）比较，正好 20% 不触发
        if s["source"].startswith("lingxing") and old_d > 0 and new_d > 0 and new_d < old_d * (1 - Decimal(str(PRICE_DROP_RATIO))):
            drops.append(f"{s['sku']}（{old:.2f} → {new:.2f}）")
    # S9-step3：SKU 在产品库里有只差大小写的多条、又没有原样相同的 → 不任选一条，提示冲突
    try:
        from fba_tool.master_db import sku_conflicts_for

        conflicts = sku_conflicts_for([s["sku"] for s in sources])
    except Exception:  # noqa: BLE001
        conflicts = {}
    if conflicts:
        warnings.append({
            "code": "sku_case_conflict",
            "skus": list(conflicts),
            "message": "以下 SKU 在产品库里有多条只差大小写/全角半角的记录，没有自动选择，产品资料和申报价都没取：" + "；".join(
                f"{k}（库里有 {'、'.join(v)}）" for k, v in conflicts.items()) + "。请先在产品库里确认（改名或删除多余的一条）。",
        })
    if drops:
        warnings.append({
            "code": "price_drop",
            "skus": [d.split("（")[0] for d in drops],
            "message": "领星实时售价比历史申报价低很多，请确认：" + "；".join(drops),
        })
    return sources, warnings, blocking


def apply_overrides(data: CustomsPackageData, overrides: Dict[str, Any] | None) -> CustomsPackageData:
    if not overrides:
        return data
    for key in (
        "order_no", "buyer", "trade_term", "total_pieces", "total_gross_kg",
        "total_net_kg", "total_qty", "total_amount", "remarks", "amount_in_words",
        "main_goods_name", "dest_country", "trade_country",
        "loading_port", "entrust_valid_until", "declare_mode",
    ):
        if key in overrides and overrides[key] not in (None, ""):
            setattr(data, key, overrides[key])
    if overrides.get("dates") and isinstance(overrides["dates"], dict):
        data.dates.update({k: str(v) for k, v in overrides["dates"].items() if v})
    line_overrides = overrides.get("lines")
    if isinstance(line_overrides, list):
        by_seq = {int(o.get("seq", i + 1)): o for i, o in enumerate(line_overrides) if isinstance(o, dict)}
        for line in data.lines:
            ov = by_seq.get(line.seq)
            if not ov:
                continue
            for fld in (
                "chinese_name", "hs_code", "qty", "unit", "unit_price", "amount",
                "brand", "model", "declare_elements", "box_count", "gross_kg", "net_kg",
            ):
                if fld in ov and ov[fld] not in (None, ""):
                    setattr(line, fld, ov[fld])
    return data


def build_customs_data(
    pairs: List[ShipmentPair],
    step1_rows: List[Dict[str, Any]],
    profile: Dict[str, Any],
    *,
    source: str,
    invoice_draft: Dict[str, Any] | None = None,
    order_no: str = "",
    dates: Dict[str, str] | None = None,
    overrides: Dict[str, Any] | None = None,
    selected_shipment_ids: List[str] | None = None,
    declaration_date: str = "",
    fx_snapshot: Dict[str, Any] | None = None,
) -> CustomsPackageData:
    source_place = str(profile.get("domestic_source") or profile.get("signed_at") or "武汉").strip() or "武汉"
    selected = _normalize_selected_ids(selected_shipment_ids)
    if source == "invoice" and invoice_draft:
        raw_rows = _rows_from_invoice_draft(invoice_draft)
        if selected is not None:
            # 仅保留勾选货件的发票行；无 shipment_id 归属的行无法判定，保守保留。
            raw_rows = [
                r for r in raw_rows
                if not str(r.get("shipment_id") or "").strip()
                or str(r["shipment_id"]).strip().upper() in selected
            ]
    else:
        raw_rows = _sku_rows_from_pairs(
            pairs, step1_rows, declaration_date=declaration_date, fx_snapshot=fx_snapshot,
        )

    lines = _merge_rows(raw_rows, source_place)
    price_sources, warnings, blocking = price_checks(raw_rows)
    cfg_missing = [str(r["config_missing"]) for r in raw_rows if r.get("config_missing")]
    if cfg_missing:
        msg = "缺报关配置（品类+HS 没有申报要素模板），不能导出：" + "、".join(dict.fromkeys(cfg_missing)) + "。请在产品库的 HS 配置里录入。"
        warnings.append({"code": "customs_config_missing", "skus": list(dict.fromkeys(cfg_missing)), "message": msg})
        blocking.append({"code": "customs_config_missing", "skus": list(dict.fromkeys(cfg_missing)), "message": msg})
    total_qty = float(money_half_up(sum((to_dec(l.qty) for l in lines), Decimal("0"))))
    total_amount = float(money_half_up(sum((to_dec(l.amount) for l in lines), Decimal("0"))))
    total_boxes = _count_total_boxes(pairs) or sum(l.box_count for l in lines)
    # v5 Q2：毛重 = Σ单箱重。货件来源时直接按箱累加（混装箱不重复计）
    spec_gross = Decimal("0")
    if source != "invoice":
        for pair in pairs:
            ship = pair.csv
            if ship.box_specs is not None and not ship.box_specs.empty and "实重(kg)" in ship.box_specs.columns:
                spec_gross += sum((to_dec(v) for v in ship.box_specs["实重(kg)"].fillna(0)), Decimal("0"))
    if spec_gross > 0:
        total_gross = float(money_half_up(spec_gross))
    else:
        total_gross = float(money_half_up(sum((to_dec(l.gross_kg) for l in lines), Decimal("0"))))
    if total_gross and total_boxes:
        total_net = compute_net_weight(
            total_gross,
            int(total_boxes),
            box_tares_for_count(int(total_boxes), step1_rows=step1_rows),
        )
    else:
        total_net = float(money_half_up(sum((to_dec(l.net_kg) for l in lines), Decimal("0"))))

    if not total_gross and pairs:
        for pair in pairs:
            ship = pair.csv
            if ship.box_specs is not None and not ship.box_specs.empty:
                col = "实重(kg)"
                if col in ship.box_specs.columns:
                    total_gross += float(ship.box_specs[col].sum())
        total_gross = float(money_half_up(total_gross))
        if not total_net:
            total_net = compute_net_weight(
                total_gross,
                int(total_boxes),
                box_tares_for_count(int(total_boxes), step1_rows=step1_rows),
            )

    merged_dates = default_dates()
    if dates:
        merged_dates.update({k: str(v) for k, v in dates.items() if v})
    _apply_date_rules(merged_dates)

    main_goods = "、".join(l.chinese_name for l in lines[:3])
    hs_summary = "、".join(dict.fromkeys(l.hs_code for l in lines if l.hs_code))

    data = CustomsPackageData(
        exporter=dict(profile),
        order_no=order_no.strip(),
        buyer=DEFAULT_BUYER,
        total_pieces=int(total_boxes),
        total_gross_kg=total_gross,
        total_net_kg=total_net,
        total_qty=total_qty,
        total_amount=total_amount,
        remarks=_build_remarks(order_no, pairs),
        lines=lines,
        dates=merged_dates,
        amount_in_words=amount_to_english_words(total_amount),
        main_goods_name=main_goods,
        hs_codes_summary=hs_summary,
        source=source,
        price_sources=price_sources,
        warnings=warnings,
        blocking=blocking,
    )
    for line in data.lines:
        line.source_place = source_place
    data.shipment_ids = list(dict.fromkeys(str(p.shipment_id or "").strip() for p in pairs if str(p.shipment_id or "").strip()))
    data.declare_mode = declare_mode_for(data.shipment_ids)

    # 第4项：口岸/征免性质/运输方式默认值取 customs_rule_profile（每票仍可用 overrides 改）
    try:
        from fba_tool.warehouse_db import get_default_rule_profile

        rp = get_default_rule_profile()
    except Exception:
        rp = {}
    for attr in ("loading_port", "exemption_nature", "transport_mode", "trade_term", "declared_value_basis", "net_weight_mode"):
        if rp.get(attr):
            setattr(data, attr, str(rp[attr]))

    data = apply_overrides(data, overrides)
    if not data.amount_in_words and data.total_amount:
        data.amount_in_words = amount_to_english_words(data.total_amount)
    from fba_tool.customs_package import attach_quote_snapshot

    attach_quote_snapshot(data, raw_rows)
    return data


# ---------------------------------------------------------------- S3：按票装配（发票/票级数据 → 报关单）
def _hs_fields(sku: str, category: str, hs: str, brand: str, material: str, purpose: str) -> Tuple[str, str, str]:
    """返回 (declare_elements, purpose, config_missing)。逻辑同 _sku_rows_from_pairs。"""
    from fba_tool.hs_config import LEGACY_DEFAULT_CATEGORY, get_hs_template, render_elements

    tpl = get_hs_template(category, hs) if hs else None
    if tpl:
        return (render_elements(tpl, {"用途": purpose, "材质": material, "品牌": brand, "型号": "无型号"}),
                purpose or str(tpl.get("default_purpose") or ""), "")
    if category != LEGACY_DEFAULT_CATEGORY:
        return "", purpose, f"{sku}（品类 {category}，HS {hs or '空'}）"
    return "", purpose or "宠物用品", ""


def _two_decimals(v: Any) -> bool:
    d = to_dec(v)
    return d == d.quantize(_CENT)


def build_customs_from_tickets(
    tickets: List[Dict[str, Any]],
    profile: Dict[str, Any],
    *,
    order_no: str,
    dates: Dict[str, str] | None = None,
    overrides: Dict[str, Any] | None = None,
) -> CustomsPackageData:
    """按票（每票 = 一个 FBA）装配报关数据。

    ticket = {shipment_id, warehouse, boxes:[单箱毛重…] 或 box_count + gross_kg, lines:[{sku, qty, unit_price?, amount?,
    chinese_name?, hs_code?, unit?, brand?, material?, purpose?, category?, box_count?, gross_kg?}]}
    行上没给的品名/HS/单位/品牌/品类/申报价取产品库（_catalog_hints）。
    毛重 = Σ单箱重（v5 Q2）；净重按 customs_rule_profile；单价 = HALF_UP(Σ申报额/Σ数量)；总价 = 凑整单价 × 数量（v6 Q3）。
    """
    source_place = str(profile.get("domestic_source") or profile.get("signed_at") or "武汉").strip() or "武汉"
    raw_rows: List[Dict[str, Any]] = []
    blocking_extra: List[Dict[str, Any]] = []
    fwd_mismatch: List[str] = []
    tol = _forwarder_tolerance()
    total_boxes = 0
    total_gross = Decimal("0")
    bad_weights: List[str] = []
    for t in tickets:
        sid = str(t.get("shipment_id") or "").strip()
        boxes = t.get("boxes")
        if boxes:
            for i, w in enumerate(boxes, start=1):
                if not _two_decimals(w):
                    bad_weights.append(f"{sid} 第{i}箱 {w}")
            t_boxes = len(boxes)
            t_gross = sum((to_dec(w) for w in boxes), Decimal("0"))
        else:
            t_boxes = int(t.get("box_count") or 0)
            t_gross = to_dec(t.get("gross_kg") or 0)
            if t.get("gross_kg") not in (None, "") and not _two_decimals(t_gross):
                bad_weights.append(f"{sid} 毛重 {t.get('gross_kg')}")
        total_boxes += t_boxes
        total_gross += t_gross
        if boxes and t.get("gross_kg") not in (None, ""):
            fwd = to_dec(t["gross_kg"])
            if abs(money_half_up(fwd) - money_half_up(t_gross)) > tol:
                fwd_mismatch.append(f"{sid}：Σ单箱重 {money_half_up(t_gross)} kg，货代报 {money_half_up(fwd)} kg，差 {money_half_up(fwd - t_gross)} kg")
        lines = t.get("lines") or []
        row_start = len(raw_rows)
        keys = {(str(l.get("chinese_name") or ""), str(l.get("hs_code") or "")) for l in lines}
        single_key = len(keys) == 1
        for ln in lines:
            sku = str(ln.get("sku") or "").strip()
            hints = _catalog_hints(sku) if sku else {}
            qty = to_dec(ln.get("qty") or 0)
            chinese = str(ln.get("chinese_name") or hints.get("中文品名") or sku).strip()
            hs = str(ln.get("hs_code") or hints.get("海关编码") or "").strip()
            brand = str(ln.get("brand") or hints.get("品牌") or "").strip()
            material = str(ln.get("material") or hints.get("材料") or "").strip()
            purpose = str(ln.get("purpose") or hints.get("用途") or "").strip()
            from fba_tool.hs_config import LEGACY_DEFAULT_CATEGORY

            category = str(ln.get("category") or hints.get("品类") or "").strip().lower() or LEGACY_DEFAULT_CATEGORY
            elements, purpose, cfg_missing = _hs_fields(sku or chinese, category, hs, brand, material, purpose)
            unit = str(ln.get("unit") or hints.get("declare_unit") or hints.get("申报单位") or DEFAULT_UNIT).strip() or DEFAULT_UNIT
            price_source, raw_price, unit_price, amount = "none", None, 0.0, 0.0
            quote_hints = None
            if ln.get("amount") not in (None, "") and qty:
                amount_d = to_dec(ln["amount"])
                raw_price = float(amount_d / qty)
                price_source = "invoice"
            elif ln.get("unit_price") not in (None, ""):
                raw_price = float(to_dec(ln["unit_price"]))
                amount_d = to_dec(ln["unit_price"]) * qty
                price_source = "invoice"
            elif hints:
                amount_d = Decimal("0")
                quote_hints = hints
            else:
                amount_d = Decimal("0")
                quote_hints = None
            if raw_price is not None and raw_price > 0:
                unit_price = float(money_half_up(raw_price))
                amount = float(amount_d)
            else:
                price_source, raw_price = "none", None
            if ln.get("box_count") not in (None, ""):
                l_boxes, l_gross = int(ln["box_count"]), to_dec(ln.get("gross_kg") or 0)
            elif single_key:
                l_boxes, l_gross = (t_boxes, t_gross) if ln is lines[0] else (0, Decimal("0"))
            else:
                l_boxes, l_gross = 0, Decimal("0")
            # S3-fix2：每票先算自己的行净重，合并时按品名相加（混装票 + 单品名票同名时不漏单品名票那份）
            l_net = (
                compute_net_weight(float(l_gross), l_boxes, box_tares_for_count(l_boxes, sku=sku))
                if l_gross and l_boxes
                else 0.0
            )
            raw_rows.append({
                "chinese_name": chinese, "hs_code": hs, "qty": float(qty), "unit": unit,
                "unit_price": unit_price, "amount": amount, "brand": brand, "model": "无型号",
                "material": material, "purpose": purpose, "box_count": l_boxes, "gross_kg": float(l_gross),
                "net_kg": l_net, "warehouse": str(t.get("warehouse") or ""), "shipment_id": sid, "sku": sku or chinese,
                "category": category, "declare_elements": elements, "config_missing": cfg_missing,
                "price_source": price_source, "legacy_price": hints.get("历史申报价"),
                "manual_price": hints.get("手填申报价"), "raw_price": raw_price,
                "promo_price": hints.get("促销售价"),
                "_quote_hints": quote_hints,
            })
        alloc_rows = raw_rows[row_start:]
        if alloc_rows and not single_key and all(ln.get("box_count") in (None, "") for ln in lines):
            _allocate_mixed(alloc_rows, t_boxes, t_gross)
    if bad_weights:
        msg = "单箱重超过 2 位小数，不做静默舍入，请修正后再导出：" + "、".join(bad_weights)
        blocking_extra.append({"code": "weight_precision", "skus": bad_weights, "message": msg})

    from fba_tool.customs_package import _apply_declared_quote

    _apply_declared_quote(raw_rows, declaration_date=str(dates.get("declare_date") or "") if dates else "")
    lines_out = _merge_rows(raw_rows, source_place)
    price_sources, warnings, blocking = price_checks(raw_rows)
    cfg = list(dict.fromkeys(str(r["config_missing"]) for r in raw_rows if r.get("config_missing")))
    if cfg:
        msg = "缺报关配置（品类+HS 没有申报要素模板），不能导出：" + "、".join(cfg) + "。请在产品库的 HS 配置里录入。"
        warnings.append({"code": "customs_config_missing", "skus": cfg, "message": msg})
        blocking.append({"code": "customs_config_missing", "skus": cfg, "message": msg})
    blocking = blocking_extra + blocking
    warnings = blocking_extra + warnings
    if fwd_mismatch:
        warnings.append({"code": "forwarder_gross_mismatch", "skus": fwd_mismatch,
                         "message": f"货代报的毛重和单箱重合计差超过 {tol} kg（v5 Q2：毛重按 Σ单箱重，货代毛重只做提示）：" + "；".join(fwd_mismatch)})
    zero = [l.chinese_name for l in lines_out if (l.gross_kg or 0) <= 0 or (l.net_kg or 0) <= 0]
    if zero and total_gross > 0:
        warnings.append({"code": "zero_weight_line", "skus": zero,
                         "message": "分摊后这些行毛重或净重为 0（总重太小、品名太多），表头合计仍正确，请人工核对装箱单：" + "、".join(zero)})

    gross_f = float(money_half_up(total_gross))
    net_f = (
        compute_net_weight(gross_f, total_boxes, box_tares_for_count(total_boxes))
        if gross_f and total_boxes
        else 0.0
    )
    total_qty = float(money_half_up(sum((to_dec(l.qty) for l in lines_out), Decimal("0"))))
    total_amount = float(money_half_up(sum((to_dec(l.amount) for l in lines_out), Decimal("0"))))
    remarks = _remarks_from(order_no, [(str(t.get("warehouse") or ""), str(t.get("shipment_id") or "")) for t in tickets])
    merged_dates = default_dates()
    if dates:
        merged_dates.update({k: str(v) for k, v in dates.items() if v})
    _apply_date_rules(merged_dates)
    data = CustomsPackageData(
        exporter=dict(profile), order_no=order_no.strip(), total_pieces=int(total_boxes),
        total_gross_kg=gross_f, total_net_kg=net_f, total_qty=total_qty, total_amount=total_amount,
        remarks=remarks, lines=lines_out, dates=merged_dates,
        amount_in_words=amount_to_english_words(total_amount),
        main_goods_name="、".join(l.chinese_name for l in lines_out[:3]),
        hs_codes_summary="、".join(dict.fromkeys(l.hs_code for l in lines_out if l.hs_code)),
        source="tickets", price_sources=price_sources, warnings=warnings, blocking=blocking,
        shipment_ids=list(dict.fromkeys(str(t.get("shipment_id") or "").strip() for t in tickets if str(t.get("shipment_id") or "").strip())),
    )
    data.declare_mode = declare_mode_for(data.shipment_ids)
    rp = _rule_profile()
    for attr in ("loading_port", "exemption_nature", "transport_mode", "trade_term", "declared_value_basis", "net_weight_mode"):
        if rp.get(attr):
            setattr(data, attr, str(rp[attr]))
    data = apply_overrides(data, overrides)
    from fba_tool.customs_package import attach_quote_snapshot

    attach_quote_snapshot(data, raw_rows)
    return data


def _remarks_from(order_no: str, pairs: List[Tuple[str, str]]) -> str:
    whs = list(dict.fromkeys(w.strip() for w, _ in pairs if w.strip()))
    fbas = list(dict.fromkeys(f.strip() for _, f in pairs if f.strip()))
    parts = [f"订单编号：{order_no}"]
    if whs:
        parts.append(f"仓库编码：{'，'.join(whs)}")
    if fbas:
        parts.append(f"FBA编码：{'，'.join(fbas)}")
    return "。".join(parts) + "。"


# ---------------------------------------------------------------- S3：订单号 / 单独合并 / 文件名 / 一致性校验
DECLARE_MODES = ("单独", "合并")
EXPORT_FORMATS = ("xlsx", "xls")


def suggest_order_no(batch: Any, code: Optional[str], boxes: int, suffix: str = "", *, fba_count: int = 1) -> str:
    """JUS{批次}{代码}{箱数}{后缀}。代码含义未定（规则清单 §4.2），只给建议：1 个 FBA 默认 DD，多个默认 HB。"""
    c = (code or ("DD" if fba_count <= 1 else "HB")).strip().upper()
    return f"JUS{str(batch).strip()}{c}{int(boxes)}{str(suffix or '').strip().upper()}"


def declare_mode_for(shipment_ids: List[str], override: str = "") -> str:
    """v6 Q5：1 个 FBA = 单独，多个 = 合并；手动改过的按手动值。"""
    o = str(override or "").strip().replace("报关", "")
    if o in DECLARE_MODES:
        return o
    return "单独" if len([s for s in shipment_ids if s]) <= 1 else "合并"


def customs_filename(order_no: str, shipment_ids: List[str], fmt: str = "xlsx", override: str = "") -> str:
    """{订单号}[-{FBA号}]-{合并|单独}报关-9810-报关资料.{xlsx|xls}；只有 1 个 FBA 时带 FBA 号。"""
    ext = str(fmt or "xlsx").lower().lstrip(".")
    if ext not in EXPORT_FORMATS:
        raise ValueError(f"导出格式只能是 xlsx 或 xls：{fmt}")
    ids = [s for s in shipment_ids if s]
    mode = declare_mode_for(ids, override)
    head = f"{order_no}-{ids[0]}" if len(ids) == 1 else order_no
    return f"{head}-{mode}报关-9810-报关资料.{ext}"


_ORDER_IN_REMARKS = __import__("re").compile(r"订单编号[：:]\s*([^。；;\s]+)")


def _issue(code: str, message: str) -> Dict[str, Any]:
    return {"code": code, "message": message}


def consistency_checks(data: "CustomsPackageData") -> List[Dict[str, Any]]:
    """导出前一致性校验（v8 §3.6）。返回阻断项列表，空 = 通过。"""
    out: List[Dict[str, Any]] = []
    order = str(data.order_no or "").strip()
    if not order:
        out.append(_issue("order_no_missing", "订单号（合同协议号）为空"))
    pieces = data.total_pieces
    if isinstance(pieces, bool) or not isinstance(pieces, (int, float)) or float(pieces) != int(float(pieces)) or int(float(pieces)) <= 0:
        out.append(_issue("pieces_not_int", f"件数必须是正整数：{pieces!r}"))
    try:
        if to_dec(data.total_net_kg) > to_dec(data.total_gross_kg):
            out.append(_issue("net_gt_gross", f"净重 {data.total_net_kg} 大于毛重 {data.total_gross_kg}"))
    except Exception:  # noqa: BLE001
        out.append(_issue("weight_not_number", "毛重/净重不是数字"))
    try:
        if isinstance(pieces, (int, float)) and float(pieces) > 0:
            if to_dec(data.total_gross_kg or 0) <= 0:
                out.append(_issue("gross_not_positive", f"件数 {pieces} 但毛重为 {data.total_gross_kg}，毛重必须 > 0"))
            if to_dec(data.total_net_kg or 0) <= 0:
                out.append(_issue("net_not_positive", f"件数 {pieces} 但净重为 {data.total_net_kg}，净重必须 > 0"))
    except Exception:  # noqa: BLE001
        pass
    if data.source == "tickets" and len(data.lines) > 1:
        lg = sum((to_dec(l.gross_kg or 0) for l in data.lines), Decimal("0"))
        ln_ = sum((to_dec(l.net_kg or 0) for l in data.lines), Decimal("0"))
        lb = sum(int(l.box_count or 0) for l in data.lines)
        if lg and money_half_up(lg) != money_half_up(data.total_gross_kg):
            out.append(_issue("lines_gross_mismatch", f"箱单明细毛重合计 {money_half_up(lg)} ≠ 总毛重 {data.total_gross_kg}"))
        if ln_ and money_half_up(ln_) != money_half_up(data.total_net_kg):
            out.append(_issue("lines_net_mismatch", f"箱单明细净重合计 {money_half_up(ln_)} ≠ 总净重 {data.total_net_kg}"))
        if lb and isinstance(pieces, (int, float)) and lb != int(float(pieces)):
            out.append(_issue("pieces_mismatch", f"件数 {pieces} 与箱单明细箱数合计 {lb} 不一致"))
    line_qty = sum((to_dec(l.qty) for l in data.lines), Decimal("0"))
    if data.lines and to_dec(data.total_qty) != line_qty:
        out.append(_issue("qty_mismatch", f"合计数量 {data.total_qty} 与明细合计 {line_qty} 不一致（发票/箱单/合同会对不上）"))
    line_boxes = sum(int(l.box_count or 0) for l in data.lines)
    # 只有 1 行时箱单明细箱数必须等于件数（多行时混装箱会被各行重复计数，不比）
    if len(data.lines) == 1 and line_boxes and isinstance(pieces, (int, float)) and int(float(pieces)) != line_boxes:
        out.append(_issue("pieces_mismatch", f"件数 {pieces} 与箱单明细箱数合计 {line_boxes} 不一致"))
    m = _ORDER_IN_REMARKS.search(str(data.remarks or ""))
    if order and m and m.group(1) != order:
        out.append(_issue("remarks_order_mismatch", f"备注里的订单编号 {m.group(1)} 与合同协议号 {order} 不一致"))
    if order:
        try:
            from fba_tool.master_db import _master_db_file
            from fba_tool.ticket_import import list_tickets

            if not _master_db_file().is_file():
                raise FileNotFoundError  # 还没有本地库：不建空库，跳过重复检查
            mine = {s.upper() for s in (data.shipment_ids or [])}
            res = list_tickets()
            rows = res.get("items", res) if isinstance(res, dict) else res
            others = sorted({str(t.get("fba_id")) for t in rows or [] if str(t.get("order_no") or "").strip() == order
                             and str(t.get("fba_id") or "").upper() not in mine})
            if others and mine:
                out.append(_issue("order_no_duplicate", f"订单号 {order} 已被其他票使用：{'、'.join(others)}"))
        except Exception:  # noqa: BLE001
            pass
    return out


def _allocate_cents(total: Decimal, weights: List[Decimal]) -> List[Decimal]:
    """最大余数法（Hamilton）：按权重把 total 分到 0.01，先向下取整到分，剩下的分按小数余数从大到小各补 1 分
    （余数相同取靠前的行）。结果全部 ≥ 0，合计严格等于 total。"""
    if not weights:
        return []
    cents = int(money_half_up(total) * 100)
    wsum = sum(weights, Decimal("0"))
    if wsum <= 0:
        weights, wsum = [Decimal(1)] * len(weights), Decimal(len(weights))
    quotas = [Decimal(cents) * w / wsum for w in weights]
    base = [int(q) for q in quotas]
    left = cents - sum(base)
    for k in sorted(range(len(quotas)), key=lambda j: (-(quotas[j] - base[j]), j))[:left]:
        base[k] += 1
    return [Decimal(b) / 100 for b in base]


def _allocate_mixed(rows: List[Dict[str, Any]], boxes: int, gross: Decimal) -> None:
    """S3-fix2 分摊规则（实现方案，规范未规定，见 D-07）：一票多品名混装、行上没给箱数时——
    箱数全部记在第一行（其余行 0，箱数合计 = 件数）；毛重、净重按件数比例用最大余数法分到 0.01，
    不会出现负数，各行合计 = 总毛重 / 总净重。分到 0 的行另出 zero_weight_line 提示（不拦截）。"""
    net = to_dec(compute_net_weight(gross, boxes, box_tares_for_count(boxes))) if gross and boxes else Decimal("0")
    w = [to_dec(r["qty"]) for r in rows]
    gs, ns = _allocate_cents(gross, w), _allocate_cents(net, w)
    for i, r in enumerate(rows):
        r["box_count"] = boxes if i == 0 else 0
        r["gross_kg"] = float(gs[i])
        r["net_kg"] = float(ns[i])
        r["net_fixed"] = True


def _forwarder_tolerance() -> Decimal:
    """S3-fix2：货代毛重差异提示容差，读 customs_rule_profile.forwarder_gross_tolerance_kg，默认 0.5 kg。"""
    try:
        from fba_tool.warehouse_db import get_default_rule_profile

        v = get_default_rule_profile().get("forwarder_gross_tolerance_kg")
    except Exception:  # noqa: BLE001
        v = None
    return to_dec(0.5 if v in (None, "") else v)
