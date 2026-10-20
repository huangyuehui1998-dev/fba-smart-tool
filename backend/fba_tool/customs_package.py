"""Step 5 报关资料 — 数据装配与合并逻辑。"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from fba_tool.master_db import get_product_by_sku, lookup_customs_name
from fba_tool.sku_keys import lookup_sku, sku_key as _norm_key, sku_text
from fba_tool.shipment_serialize import csv_shipment_from_dict
from fba_tool.shipment_validator import ShipmentPair
from fba_tool.user_config import load_settings

DEFAULT_NET_RATIO = 0.9  # 仅 customs_net_weight_method="ratio" 时使用（可选，默认不用）
DEFAULT_NET_MINUS_PER_BOX = Decimal("0.2")  # v5 Q1：净重 = 毛重 − 0.2kg × 箱数
DEFAULT_LOADING_PORT = "宁波北仑"  # v6 Q7
DEFAULT_UNIT = "件"
_CENT = Decimal("0.01")


def to_dec(v: Any) -> Decimal:
    if v is None or v == "":
        return Decimal("0")
    if isinstance(v, Decimal):
        return v
    if isinstance(v, float):
        return Decimal(repr(v))
    return Decimal(str(v))


def money_half_up(v: Any) -> Decimal:
    """金额/单价：Decimal + ROUND_HALF_UP 保留 2 位（替代内置 round 的银行家舍入）。"""
    return to_dec(v).quantize(_CENT, rounding=ROUND_HALF_UP)


def net_weight_minus_per_box(gross: Any, boxes: int, per_box: Any = DEFAULT_NET_MINUS_PER_BOX) -> Decimal:
    """净重 = 毛重 − 每箱扣重 × 箱数；毛重为 0 时返回 0。"""
    g = to_dec(gross)
    if g <= 0:
        return Decimal("0")
    return (g - to_dec(per_box) * int(boxes or 0)).quantize(_CENT, rounding=ROUND_HALF_UP)


def default_entrust_valid_until(today: Optional[date] = None) -> str:
    """委托书有效期：导出当年 12 月 31 日（v6 Q7），格式与模板 委托书!E12 一致。"""
    year = (today or date.today()).year
    return f"{year} 年 12 月 31日止。"
DEFAULT_BUYER = "Amazon"
DEFAULT_TRADE_TERM = "C&F"
DEFAULT_DEST_COUNTRY = "美国"
DEFAULT_ORIGIN = "中国"


@dataclass
class CustomsLineItem:
    seq: int = 0
    chinese_name: str = ""
    hs_code: str = ""
    qty: float = 0
    unit: str = "件"
    unit_price: float = 0
    amount: float = 0
    brand: str = ""
    model: str = "无型号"
    brand_type: str = "自主品牌"
    export_preferential: str = "出口货物不能确定在最终目的国（地区）享受优惠关税"
    declare_elements: str = ""
    quarantine_code: str = ""
    box_count: int = 0
    gross_kg: float = 0
    net_kg: float = 0
    origin_country: str = DEFAULT_ORIGIN
    dest_country: str = DEFAULT_DEST_COUNTRY
    source_place: str = "武汉"
    tax_exemption: str = "照章征税"
    price_source: str = ""  # manual / lingxing / legacy / invoice / none / mixed
    category: str = ""
    config_missing: str = ""  # 非空 = 缺报关配置（导出阻断）


@dataclass
class CustomsPackageData:
    exporter: Dict[str, Any] = field(default_factory=dict)
    order_no: str = ""
    buyer: str = DEFAULT_BUYER
    trade_term: str = DEFAULT_TRADE_TERM
    package_type: str = "纸箱"
    total_pieces: int = 0
    total_gross_kg: float = 0
    total_net_kg: float = 0
    total_qty: float = 0
    total_amount: float = 0
    remarks: str = ""
    lines: List[CustomsLineItem] = field(default_factory=list)
    dates: Dict[str, str] = field(default_factory=dict)
    amount_in_words: str = ""
    main_goods_name: str = ""
    hs_codes_summary: str = ""
    supervision_mode: str = "9810"
    exemption_nature: str = "101"
    transport_mode: str = "海路运输"
    dest_country: str = DEFAULT_DEST_COUNTRY
    trade_country: str = DEFAULT_DEST_COUNTRY
    discharge_country: str = DEFAULT_DEST_COUNTRY
    loading_port: str = DEFAULT_LOADING_PORT
    entrust_valid_until: str = field(default_factory=default_entrust_valid_until)
    freight: str = ""  # v6 Q11：运费一律留空
    payment_terms: str = "电汇"
    currency: str = "USD"
    source: str = "shipment"
    # S2-fix D2：申报价来源与提示。warnings 只提示；blocking 有内容时导出会被拦下
    price_sources: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    blocking: List[Dict[str, Any]] = field(default_factory=list)
    # S3：本单包含的 FBA、单独/合并（1 个 FBA = 单独，多个 = 合并，可手改）
    shipment_ids: List[str] = field(default_factory=list)
    declare_mode: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["lines"] = [asdict(line) for line in self.lines]
        return d


def _today() -> date:
    return date.today()


def default_dates() -> Dict[str, str]:
    today = _today()
    ship = today + timedelta(days=15)
    iso = today.isoformat()
    return {
        # v6 Q16：出口日期、申报日期申报时免予填报，默认留空
        "export_date": "",
        "declare_date": "",
        "invoice_date": iso,
        "contract_date": iso,
        "packing_date": iso,
        "shipment_deadline": ship.isoformat(),
        "entrust_import_export_date": (today + timedelta(days=1)).isoformat(),
        "entrust_doc_received_date": iso,
        "entrust_sign_date": (today - timedelta(days=1)).isoformat(),
    }


def _rule_profile() -> Dict[str, Any]:
    try:
        from fba_tool.warehouse_db import get_default_rule_profile

        return get_default_rule_profile() or {}
    except Exception:  # noqa: BLE001
        return {}


def _apply_date_rules(dates: Dict[str, str]) -> None:
    """v6 Q16：出口/申报日期默认留空；customs_rule_profile.fill_export_declare_date 打开时默认取 etd（开船日）。"""
    rp = _rule_profile()
    etd = str(dates.get("etd") or "").strip()
    if int(rp.get("fill_export_declare_date") or 0) and etd:
        dates.setdefault("export_date", "")
        dates.setdefault("declare_date", "")
        if not dates["export_date"]:
            dates["export_date"] = etd
        if not dates["declare_date"]:
            dates["declare_date"] = etd


def _net_weight_params() -> Tuple[str, Decimal, Decimal]:
    """S3：净重规则只认 customs_rule_profile（不再读用户设置里的 customs_net_weight_*）。"""
    rp = _rule_profile()
    method = str(rp.get("net_weight_mode") or "minus_per_box").strip()
    per_box = DEFAULT_NET_MINUS_PER_BOX if rp.get("net_minus_per_box") in (None, "") else to_dec(rp["net_minus_per_box"])
    ratio = to_dec(DEFAULT_NET_RATIO) if rp.get("net_ratio") in (None, "") else to_dec(rp["net_ratio"])
    return method, per_box, ratio


def compute_net_weight(gross: Any, boxes: int) -> float:
    method, per_box, ratio = _net_weight_params()
    if method == "ratio":
        return float(money_half_up(to_dec(gross) * ratio))
    return float(net_weight_minus_per_box(gross, boxes, per_box))


def _weight_map_from_step1(step1_rows: List[Dict[str, Any]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for row in step1_rows or []:
        sku = sku_text(row.get("SKU") or row.get("sku") or "")  # S9-step4-fix3：原样写法作键
        if not sku:
            continue
        for key in ("单个重量(kg)", "unit_weight_kg", "单个重量"):
            val = row.get(key)
            if val not in (None, ""):
                try:
                    out[sku] = float(val)
                except (TypeError, ValueError):
                    pass
                break
    return out


def pairs_from_workflow(
    workflow: Dict[str, Any],
    selected_shipment_ids: List[str] | None = None,
) -> List[ShipmentPair]:
    """从 workflow 还原货件对；selected_shipment_ids 非空时仅保留勾选的 FBA 货件。"""
    from fba_tool.shipment_parser import PdfShipment

    selected = _normalize_selected_ids(selected_shipment_ids)

    pairs: List[ShipmentPair] = []
    for item in workflow.get("shipments") or []:
        if not isinstance(item, dict):
            continue
        ship = csv_shipment_from_dict(item.get("parsed_shipment"))
        if ship is None or ship.box_items.empty:
            continue
        sid = str(item.get("shipment_id") or ship.shipment_id or "").upper()
        if selected is not None and sid not in selected:
            continue
        wh = str(item.get("warehouse") or ship.warehouse_code or "").strip()
        pairs.append(
            ShipmentPair(
                shipment_id=sid,
                warehouse_code=wh,
                csv=ship,
                pdf=PdfShipment(shipment_id=sid, page_count=0, pages=[]),
                pdf_name="",
            )
        )
    return pairs


def _normalize_selected_ids(selected_shipment_ids: List[str] | None) -> set[str] | None:
    """统一为大写集合；None 或空列表表示「全选」返回 None。"""
    if not selected_shipment_ids:
        return None
    ids = {str(s).strip().upper() for s in selected_shipment_ids if str(s).strip()}
    return ids or None


def _catalog_hints(sku: str) -> Dict[str, Any]:
    from fba_tool.master_db import invoice_hints_from_master

    master = get_product_by_sku(sku)
    merged = invoice_hints_from_master(master)
    if master and master.get("unit_weight"):
        merged["单品净重"] = master["unit_weight"]
    cn = lookup_customs_name(sku)
    if cn:
        merged.setdefault("中文品名", cn)
    return merged


def _build_declare_elements(chinese: str, brand: str, model: str, material: str = "", purpose: str = "") -> str:
    parts = ["1", "2"]
    if purpose:
        parts.append(purpose)
    elif material:
        parts.append(material)
    else:
        parts.append("宠物用")
    brand_part = brand or "无品牌"
    model_part = model if model and model != "无型号" else "无型号"
    parts.append(f"品牌：{brand_part}牌")
    parts.append(f"型号：{model_part}")
    return "|".join(parts)


def _sku_rows_from_pairs(
    pairs: List[ShipmentPair],
    step1_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    weight_map = _weight_map_from_step1(step1_rows)
    rows: List[Dict[str, Any]] = []

    for pair in pairs:
        ship = pair.csv
        if ship.box_items.empty:
            continue
        grouped = ship.box_items.groupby("SKU", sort=True)
        spec_map: Dict[int, float] = {}
        if not ship.box_specs.empty and "箱号" in ship.box_specs.columns:
            for _, spec in ship.box_specs.iterrows():
                try:
                    box_no = int(spec["箱号"])
                    spec_map[box_no] = float(spec.get("实重(kg)", 0) or 0)
                except (TypeError, ValueError):
                    continue

        for sku, grp in grouped:
            sku_str = str(sku).strip()
            boxes = sorted(int(b) for b in grp["箱号"].tolist())
            qty = int(grp["数量"].sum())
            box_count = len(boxes)
            gross = float(money_half_up(sum((to_dec(spec_map.get(b, 0)) for b in boxes), Decimal("0"))))

            hints = _catalog_hints(sku_str)
            chinese = str(hints.get("中文品名") or sku_str).strip()
            hs = str(hints.get("海关编码") or "").strip()
            brand = str(hints.get("品牌") or "").strip()
            material = str(hints.get("材料") or "").strip()
            # 第3项：申报要素按 品类+HS 取 hs_declare_template；非宠物品类缺模板 → 缺报关配置，不套宠物模板
            from fba_tool.hs_config import LEGACY_DEFAULT_CATEGORY, get_hs_template, render_elements

            category = str(hints.get("品类") or "").strip().lower() or LEGACY_DEFAULT_CATEGORY
            tpl = get_hs_template(category, hs) if hs else None
            raw_purpose = str(hints.get("用途") or "").strip()
            config_missing = ""
            elements = ""
            if tpl:
                elements = render_elements(tpl, {"用途": raw_purpose, "材质": material, "品牌": brand, "型号": "无型号"})
                purpose = raw_purpose or str(tpl.get("default_purpose") or "")
            elif category != LEGACY_DEFAULT_CATEGORY:
                purpose = raw_purpose
                config_missing = f"{sku_str}（品类 {category}，HS {hs or '空'}）"
            else:
                purpose = raw_purpose or "宠物用品"
            # S2-fix D2：没有申报价时不再静默填 0，标记 none，由 build_customs_data 阻断导出
            unit_price = 0.0
            raw_price = None
            price_source = "none"
            if hints.get("单个货值") not in (None, ""):
                try:
                    raw_price = float(hints["单个货值"])  # s2-final：原值留给提示判断，不先四舍五入
                    unit_price = float(money_half_up(raw_price))
                    price_source = str(hints.get("申报价来源") or "legacy")
                except (TypeError, ValueError):
                    unit_price = 0.0
            if unit_price <= 0:
                unit_price, price_source = 0.0, "none"
            legacy_price = hints.get("历史申报价")
            manual_price = hints.get("手填申报价")
            promo_price = hints.get("促销售价")

            unit_net = lookup_sku(weight_map, sku_str)  # S9-step3：统一大小写 / 全角规则
            if unit_net is None and hints.get("单品净重") not in (None, ""):
                try:
                    unit_net = float(hints["单品净重"])
                except (TypeError, ValueError):
                    unit_net = None

            net = 0.0
            if unit_net and qty:
                net = float(money_half_up(to_dec(unit_net) * qty))
            elif gross:
                net = compute_net_weight(gross, box_count)

            rows.append(
                {
                    "chinese_name": chinese,
                    "hs_code": hs,
                    "qty": qty,
                    "unit": str(hints.get("declare_unit") or hints.get("申报单位") or DEFAULT_UNIT).strip() or DEFAULT_UNIT,
                    "unit_price": unit_price,
                    "amount": float(money_half_up(to_dec(unit_price) * qty)) if unit_price and qty else 0.0,
                    "brand": brand,
                    "model": "无型号",
                    "material": material,
                    "purpose": purpose,
                    "box_count": box_count,
                    "gross_kg": gross,
                    "net_kg": net,
                    "warehouse": pair.warehouse_code,
                    "shipment_id": pair.shipment_id,
                    "sku": sku_str,
                    "category": category,
                    "declare_elements": elements,
                    "config_missing": config_missing,
                    "price_source": price_source,
                    "legacy_price": legacy_price,
                    "manual_price": manual_price,
                    "promo_price": promo_price,
                    "raw_price": raw_price,
                    # 混装箱：同一箱可能出现在多行，合并时按箱去重（件数/毛重不重复计）
                    "box_weights": {f"{pair.shipment_id}#{b}": spec_map.get(b, 0) for b in boxes},
                }
            )
    return rows


def _rows_from_invoice_draft(invoice_draft: Dict[str, Any]) -> List[Dict[str, Any]]:
    cells = invoice_draft.get("cells") or []
    if not cells:
        return []

    by_row: Dict[int, Dict[str, Any]] = defaultdict(dict)
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        ref = str(cell.get("cell") or "").upper()
        key = str(cell.get("field_key") or cell.get("key") or "")
        val = cell.get("value", "")
        if not ref or not key:
            continue
        row_num = int("".join(c for c in ref if c.isdigit()) or "0")
        if row_num <= 0:
            continue
        by_row[row_num][key] = val

    rows: List[Dict[str, Any]] = []
    for row_num in sorted(by_row.keys()):
        data = by_row[row_num]
        sku = str(data.get("sku") or "").strip()
        if not sku and not data.get("chinese_name"):
            continue
        qty = data.get("total_qty") or data.get("qty") or 0
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            qty = 0
        if qty <= 0:
            continue
        declared = data.get("declared_price") or data.get("unit_price") or 0
        try:
            declared = float(money_half_up(declared))
        except (TypeError, ValueError, ArithmeticError):
            declared = 0
        total_val = data.get("total_declared_value_usd")
        try:
            amount = float(money_half_up(total_val)) if total_val not in (None, "") else float(money_half_up(to_dec(declared) * to_dec(qty)))
        except (TypeError, ValueError, ArithmeticError):
            amount = float(money_half_up(to_dec(declared) * to_dec(qty)))

        box_count = data.get("box_count") or 0
        try:
            box_count = int(box_count)
        except (TypeError, ValueError):
            box_count = 0

        gross = data.get("box_weight") or data.get("total_weight_kg") or 0
        try:
            gross = float(money_half_up(gross))
        except (TypeError, ValueError, ArithmeticError):
            gross = 0

        unit_w = data.get("unit_weight_kg")
        net = 0.0
        if unit_w not in (None, ""):
            try:
                net = float(money_half_up(to_dec(unit_w) * to_dec(qty)))
            except (TypeError, ValueError, ArithmeticError):
                pass
        if not net and gross:
            net = compute_net_weight(gross, box_count)

        rows.append(
            {
                "chinese_name": str(data.get("chinese_name") or "").strip(),
                "hs_code": str(data.get("hs_code") or "").strip(),
                "qty": qty,
                "unit": str(data.get("unit") or "件").strip() or "件",
                "unit_price": declared,
                "amount": amount,
                "brand": str(data.get("brand") or "").strip(),
                "model": str(data.get("model") or "无型号").strip() or "无型号",
                "material": str(data.get("material") or "").strip(),
                "purpose": str(data.get("purpose") or "宠物用品").strip(),
                "box_count": box_count,
                "gross_kg": gross,
                "net_kg": net,
                "sku": sku,
                "price_source": "invoice" if declared and declared > 0 else "none",
                "warehouse": str(data.get("shipping_mark") or invoice_draft.get("warehouse_code") or "").strip(),
                "shipment_id": str(data.get("shipment_id") or invoice_draft.get("shipment_id") or "").strip(),
            }
        )
    return rows


def _merge_rows(raw_rows: List[Dict[str, Any]], source_place: str) -> List[CustomsLineItem]:
    groups: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in raw_rows:
        cn = str(row.get("chinese_name") or "").strip()
        hs = str(row.get("hs_code") or "").strip()
        if not cn:
            continue
        key = (cn, hs)
        if key not in groups:
            groups[key] = {
                "chinese_name": cn,
                "hs_code": hs,
                "qty": 0.0,
                "unit": row.get("unit") or "件",
                "amount": 0.0,
                "brand": row.get("brand") or "",
                "model": row.get("model") or "无型号",
                "material": row.get("material") or "",
                "purpose": row.get("purpose") or "宠物用品",
                "box_count": 0,
                "gross_kg": 0.0,
                "net_kg": 0.0,
                "price_sources": set(),
                "declare_elements": "",
                "config_missing": [],
                "category": row.get("category") or "",
                "box_weights": {},
            }
        g = groups[key]
        if row.get("box_weights"):
            g["box_weights"].update(row["box_weights"])
        if row.get("declare_elements") and not g["declare_elements"]:
            g["declare_elements"] = row["declare_elements"]
        if row.get("config_missing"):
            g["config_missing"].append(row["config_missing"])
        g["price_sources"].add(str(row.get("price_source") or ""))
        g["qty"] += float(row.get("qty") or 0)
        g["amount"] += float(row.get("amount") or 0)
        g["box_count"] += int(row.get("box_count") or 0)
        g["gross_kg"] += float(row.get("gross_kg") or 0)
        g["net_kg"] += float(row.get("net_kg") or 0)
        if row.get("net_fixed"):
            g["net_fixed"] = True
        if not g["brand"] and row.get("brand"):
            g["brand"] = row["brand"]

    lines: List[CustomsLineItem] = []
    for i, g in enumerate(groups.values(), start=1):
        if g["box_weights"]:
            g["box_count"] = len(g["box_weights"])
            g["gross_kg"] = float(sum((to_dec(w) for w in g["box_weights"].values()), Decimal("0")))
        qty = g["qty"]
        # v6 Q3：单价 = HALF_UP(Σ申报额 / Σ数量, 2)；总价 = 凑整单价 × 数量
        sum_amount = to_dec(g["amount"])
        if qty:
            unit_price_d = money_half_up(sum_amount / to_dec(qty))
            amount = float(money_half_up(unit_price_d * to_dec(qty)))
            unit_price = float(unit_price_d)
        else:
            unit_price, amount = 0.0, float(money_half_up(sum_amount))
        srcs = {s for s in g["price_sources"] if s}
        if "none" in srcs:
            # 任一 SKU 缺申报价：整行单价/金额置 0 并标 none（导出会被阻断，不会带着 0 出去）
            unit_price, amount, line_src = 0.0, 0.0, "none"
        else:
            line_src = srcs.pop() if len(srcs) == 1 else ("mixed" if srcs else "")
        if g.get("net_fixed"):
            line_net = float(money_half_up(g["net_kg"]))  # 混装分摊过的净重，合计已对齐总净重
        elif g["gross_kg"] and g["box_count"]:
            line_net = compute_net_weight(g["gross_kg"], int(g["box_count"]))
        else:
            line_net = float(money_half_up(g["net_kg"]))
        brand = g["brand"] or "无品牌"
        model = g["model"] or "无型号"
        lines.append(
            CustomsLineItem(
                seq=i,
                chinese_name=g["chinese_name"],
                hs_code=g["hs_code"],
                qty=qty,
                unit=g["unit"],
                unit_price=unit_price,
                amount=amount,
                brand=brand,
                model=model,
                declare_elements=(
                    "" if g["config_missing"]
                    else g["declare_elements"]
                    or _build_declare_elements(g["chinese_name"], brand, model, g["material"], g["purpose"])
                ),
                category=g["category"],
                config_missing="、".join(g["config_missing"]),
                box_count=int(g["box_count"]),
                gross_kg=float(money_half_up(g["gross_kg"])),
                net_kg=line_net,
                source_place=source_place,
                price_source=line_src,
            )
        )
    return lines


def _build_remarks(order_no: str, pairs: List[ShipmentPair]) -> str:
    warehouses: List[str] = []
    fba_ids: List[str] = []
    seen_w: set[str] = set()
    seen_f: set[str] = set()
    for pair in pairs:
        wh = str(pair.warehouse_code or "").strip()
        if wh and wh not in seen_w:
            seen_w.add(wh)
            warehouses.append(wh)
        sid = str(pair.shipment_id or "").strip()
        if sid and sid not in seen_f:
            seen_f.add(sid)
            fba_ids.append(sid)
    parts = [f"订单编号：{order_no}"]
    if warehouses:
        parts.append(f"仓库编码：{'，'.join(warehouses)}")
    if fba_ids:
        parts.append(f"FBA编码：{'，'.join(fba_ids)}")
    return "。".join(parts) + "。"


def _count_total_boxes(pairs: List[ShipmentPair]) -> int:
    # 去重键用票的序号 + 箱号：多张“待分配”票的 shipment_id 相同，不能按票号去重（D2）
    boxes: set[Tuple[int, int]] = set()
    for idx, pair in enumerate(pairs):
        ship = pair.csv
        if ship.box_specs is not None and not ship.box_specs.empty and "箱号" in ship.box_specs.columns:
            for box in ship.box_specs["箱号"].tolist():
                try:
                    boxes.add((idx, int(box)))
                except (TypeError, ValueError):
                    continue
        elif not ship.box_items.empty and "箱号" in ship.box_items.columns:
            for box in ship.box_items["箱号"].tolist():
                try:
                    boxes.add((idx, int(box)))
                except (TypeError, ValueError):
                    continue
    return len(boxes)


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
    missing = [s["sku"] for s in sources if s["source"] == "none"]
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
        if pp in (None, "") or s.get("price") in (None, ""):
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
        raw_rows = _sku_rows_from_pairs(pairs, step1_rows)

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
        total_net = compute_net_weight(total_gross, int(total_boxes))
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
            total_net = compute_net_weight(total_gross, int(total_boxes))

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
    for attr in ("loading_port", "exemption_nature", "transport_mode"):
        if rp.get(attr):
            setattr(data, attr, str(rp[attr]))

    data = apply_overrides(data, overrides)
    if not data.amount_in_words and data.total_amount:
        data.amount_in_words = amount_to_english_words(data.total_amount)
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
            if ln.get("amount") not in (None, "") and qty:
                amount_d = to_dec(ln["amount"])
                raw_price = float(amount_d / qty)
                price_source = "invoice"
            elif ln.get("unit_price") not in (None, ""):
                raw_price = float(to_dec(ln["unit_price"]))
                amount_d = to_dec(ln["unit_price"]) * qty
                price_source = "invoice"
            elif hints.get("单个货值") not in (None, ""):
                raw_price = float(to_dec(hints["单个货值"]))
                amount_d = to_dec(hints["单个货值"]) * qty
                price_source = str(hints.get("申报价来源") or "legacy")
            else:
                amount_d = Decimal("0")
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
            l_net = compute_net_weight(float(l_gross), l_boxes) if l_gross and l_boxes else 0.0
            raw_rows.append({
                "chinese_name": chinese, "hs_code": hs, "qty": float(qty), "unit": unit,
                "unit_price": unit_price, "amount": amount, "brand": brand, "model": "无型号",
                "material": material, "purpose": purpose, "box_count": l_boxes, "gross_kg": float(l_gross),
                "net_kg": l_net, "warehouse": str(t.get("warehouse") or ""), "shipment_id": sid, "sku": sku or chinese,
                "category": category, "declare_elements": elements, "config_missing": cfg_missing,
                "price_source": price_source, "legacy_price": hints.get("历史申报价"),
                "manual_price": hints.get("手填申报价"), "raw_price": raw_price,
                "promo_price": hints.get("促销售价") if str(price_source).startswith("lingxing_") else None,
            })
        alloc_rows = raw_rows[row_start:]
        if alloc_rows and not single_key and all(ln.get("box_count") in (None, "") for ln in lines):
            _allocate_mixed(alloc_rows, t_boxes, t_gross)
    if bad_weights:
        msg = "单箱重超过 2 位小数，不做静默舍入，请修正后再导出：" + "、".join(bad_weights)
        blocking_extra.append({"code": "weight_precision", "skus": bad_weights, "message": msg})

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
    net_f = compute_net_weight(gross_f, total_boxes) if gross_f and total_boxes else 0.0
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
    for attr in ("loading_port", "exemption_nature", "transport_mode"):
        if rp.get(attr):
            setattr(data, attr, str(rp[attr]))
    data = apply_overrides(data, overrides)
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
    net = to_dec(compute_net_weight(gross, boxes)) if gross and boxes else Decimal("0")
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
