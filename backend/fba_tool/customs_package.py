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

DEFAULT_NET_RATIO = 0.95  # 仅 net_weight_mode="ratio" 时使用（非规范口径，默认不用）
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
    declared_value_basis: str = "retail"
    trade_term_source: str = "profile"
    fx_rate: Optional[float] = None
    fx_rate_type: str = ""
    fx_applicable_month: str = ""
    fx_source_url: str = ""
    fx_publish_date: str = ""
    net_weight_mode: str = "tare_from_carton"
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


_pending_tare_notes: List[str] = []


def pop_tare_notes() -> List[str]:
    notes = list(_pending_tare_notes)
    _pending_tare_notes.clear()
    return notes


def _net_weight_params() -> Tuple[str, Decimal, Decimal]:
    """S3：净重规则只认 customs_rule_profile。字段为空时用 tare_from_carton，不再回落 minus_per_box。"""
    rp = _rule_profile()
    method = str(rp.get("net_weight_mode") or "tare_from_carton").strip()
    per_box = DEFAULT_NET_MINUS_PER_BOX if rp.get("net_minus_per_box") in (None, "") else to_dec(rp["net_minus_per_box"])
    ratio = to_dec(DEFAULT_NET_RATIO) if rp.get("net_ratio") in (None, "") else to_dec(rp["net_ratio"])
    return method, per_box, ratio


def box_tares_for_count(
    box_count: int,
    *,
    sku: str = "",
    step1_rows: Optional[List[Dict[str, Any]]] = None,
    explicit: Optional[List[Any]] = None,
) -> List[Any]:
    """按箱给出皮重。顺序：调用方显式值、箱规 tare_kg、Step1 空纸箱重。缺的格子留 None。"""
    count = max(int(box_count or 0), 0)
    if explicit is not None:
        rows = list(explicit)
        if len(rows) >= count:
            return rows[:count]
        return rows + [None] * (count - len(rows))
    found = _tare_for_sku(sku, step1_rows)
    if found is None:
        return [None] * count
    return [found] * count


def _tare_for_sku(sku: str, step1_rows: Optional[List[Dict[str, Any]]]) -> Any:
    wanted = str(sku or "").strip()
    for row in step1_rows or []:
        row_sku = str(row.get("SKU") or row.get("sku") or row.get("SKU简称") or "").strip()
        if wanted and row_sku and row_sku != wanted:
            continue
        for key in ("空纸箱重(kg)", "空纸箱重", "tare_kg"):
            if row.get(key) not in (None, ""):
                return row.get(key)
    if not wanted:
        return None
    try:
        from fba_tool.carton_store import list_specs

        specs = list_specs(wanted)
    except Exception:  # noqa: BLE001
        return None
    chosen = None
    for spec in specs:
        if spec.get("tare_kg") in (None, ""):
            continue
        if spec.get("is_default"):
            return spec.get("tare_kg")
        chosen = chosen if chosen is not None else spec.get("tare_kg")
    return chosen


def compute_net_weight(
    gross: Any,
    boxes: int,
    box_tares: Optional[List[Any]] = None,
    warnings: Optional[List[Any]] = None,
) -> float:
    """净重。默认 tare_from_carton：毛重 − 各箱皮重。某一箱没有皮重时按 0.2kg 并记提示。"""
    method, per_box, ratio = _net_weight_params()
    if method == "ratio":
        return float(money_half_up(to_dec(gross) * ratio))
    if method == "minus_per_box":
        return float(net_weight_minus_per_box(gross, boxes, per_box))
    count = int(boxes or 0)
    if count <= 0:
        return 0.0
    provided = list(box_tares) if box_tares is not None else []
    tare_sum = Decimal("0")
    for index in range(count):
        tare = provided[index] if index < len(provided) else None
        if tare in (None, ""):
            tare_sum += Decimal("0.2")
            message = f"第 {index + 1} 箱缺皮重，按 0.2kg 计"
            _pending_tare_notes.append(message)
            if warnings is not None:
                warnings.append({"code": "missing_tare", "message": message})
        else:
            tare_sum += to_dec(tare)
    net = to_dec(gross) - tare_sum
    if net < 0:
        net = Decimal("0")
    return float(money_half_up(net))


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
    if master:
        if master.get("product_cost_cny") not in (None, ""):
            merged["product_cost_cny"] = master["product_cost_cny"]
        if master.get("purchase_price") not in (None, ""):
            merged["purchase_cny"] = master["purchase_price"]
        if master.get("fob_unit_value") not in (None, ""):
            merged["fob_value"] = master["fob_unit_value"]
            merged["fob_currency"] = "USD"
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


def attach_quote_snapshot(data: Any, raw_rows: List[Dict[str, Any]]) -> None:
    """把报价时用的 5 个汇率字段写回报关数据，重新导出时沿用。"""
    for row in raw_rows:
        snap = row.get("_fx_snapshot") or {}
        if not snap:
            continue
        if snap.get("fx_rate") not in (None, ""):
            data.fx_rate = snap.get("fx_rate")
            data.fx_rate_type = str(snap.get("fx_rate_type") or "")
            data.fx_applicable_month = str(snap.get("fx_applicable_month") or "")
            data.fx_source_url = str(snap.get("fx_source_url") or "")
            data.fx_publish_date = str(snap.get("fx_publish_date") or "")
        notice = str(snap.get("fob_source_notice") or "")
        if notice and notice not in (data.remarks or ""):
            data.remarks = f"{data.remarks}{notice}"
            data.warnings = list(data.warnings or []) + [
                {"code": "fob_retail_fallback", "skus": [], "message": notice}
            ]
        break


def _apply_declared_quote(
    rows: List[Dict[str, Any]],
    *,
    declaration_date: str = "",
    fx_snapshot: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """按口径走报价引擎。单个货值只进入历史申报价或领星售价，不再直接当单价。"""
    marked = [row for row in rows if row.get("_quote_hints") is not None]
    if not marked:
        return None
    from fba_tool.declared_value import FxRateRequired, quote_declared_value
    from fba_tool.fx_rates import snapshot_for_declaration

    profile = _rule_profile()
    basis = str(profile.get("declared_value_basis") or "retail")
    month = ""
    fx = fx_snapshot
    if declaration_date:
        try:
            fx = snapshot_for_declaration(declaration_date, fx_snapshot=fx_snapshot)
            month = str((fx or {}).get("fx_applicable_month") or declaration_date[:7])
        except ValueError:
            month = ""
    lines = []
    for row in marked:
        hints = row.get("_quote_hints") or {}
        source = str(hints.get("申报价来源") or "")
        unit = hints.get("单个货值")
        retail = hints.get("retail_usd")
        legacy = hints.get("历史申报价") if hints.get("历史申报价") not in (None, "") else hints.get("legacy_usd")
        manual_usd = None
        if source.startswith("lingxing") and unit not in (None, ""):
            retail = unit
        elif source == "manual" and unit not in (None, ""):
            manual_usd = unit
        elif legacy in (None, "") and unit not in (None, "") and not source.startswith("lingxing"):
            legacy = unit
        master_cost = hints.get("product_cost_cny")
        fob_value = hints.get("fob_value")
        if fob_value in (None, "") and basis == "fob":
            fob_value = manual_usd if manual_usd not in (None, "") else hints.get("手填申报价")
        lines.append({
            "sku": row.get("sku"),
            "qty": row.get("qty") or 0,
            "retail_usd": retail,
            "legacy_usd": legacy,
            "manual_usd": manual_usd,
            "product_cost_cny": master_cost,
            "purchase_cny": hints.get("purchase_cny") or hints.get("采购价"),
            "fob_value": fob_value,
            "fob_currency": hints.get("fob_currency") or "USD",
        })
    try:
        quoted = quote_declared_value(lines, basis, fx, month=month or "0000-00")
    except FxRateRequired:
        for row in marked:
            row.pop("_quote_hints", None)
        raise
    notice = str(quoted.get("fob_source_notice") or "")
    for row, item, line in zip(marked, quoted["lines"], lines):
        original = line.get("retail_usd")
        if original in (None, ""):
            original = line.get("manual_usd")
        if original in (None, ""):
            original = line.get("legacy_usd")
        row["unit_price"] = item["unit_usd"]
        row["amount"] = item["amount_usd"]
        row["price_source"] = item["price_source"]
        row["raw_price"] = original if original not in (None, "") else item["unit_usd"]
        if item.get("notice"):
            row["price_notice"] = item["notice"]
        row.pop("_quote_hints", None)
    if notice:
        quoted["fob_source_notice"] = notice
    rows_meta = quoted
    for row in marked:
        row["_fx_snapshot"] = {
            "fx_rate": quoted.get("fx_rate"),
            "fx_rate_type": quoted.get("fx_rate_type"),
            "fx_applicable_month": quoted.get("fx_applicable_month"),
            "fx_source_url": quoted.get("fx_source_url"),
            "fx_publish_date": quoted.get("fx_publish_date"),
            "fob_source_notice": notice,
        }
    return rows_meta


def _sku_rows_from_pairs(
    pairs: List[ShipmentPair],
    step1_rows: List[Dict[str, Any]],
    *,
    declaration_date: str = "",
    fx_snapshot: Optional[Dict[str, Any]] = None,
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
            # 单个货值只作为报价引擎的输入，不再直接成为单价。
            unit_price = 0.0
            raw_price = None
            price_source = "none"
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
                net = compute_net_weight(
                    gross,
                    box_count,
                    box_tares_for_count(box_count, sku=sku_str, step1_rows=step1_rows),
                )

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
                    "_quote_hints": hints,
                    # 混装箱：同一箱可能出现在多行，合并时按箱去重（件数/毛重不重复计）
                    "box_weights": {f"{pair.shipment_id}#{b}": spec_map.get(b, 0) for b in boxes},
                }
            )
    _apply_declared_quote(rows, declaration_date=declaration_date, fx_snapshot=fx_snapshot)
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
            net = compute_net_weight(gross, box_count, box_tares_for_count(box_count, sku=sku))

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
            line_net = compute_net_weight(
                g["gross_kg"],
                int(g["box_count"]),
                box_tares_for_count(int(g["box_count"]), sku=str(g.get("sku") or "")),
            )
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



# 校验与按票装配在 customs_package_checks；文末导入，保证上面的类型已经定义。
from fba_tool.customs_package_checks import (  # noqa: E402
    DECLARE_MODES,
    EXPORT_FORMATS,
    PRICE_DROP_RATIO,
    PRICE_SOURCE_LABELS,
    _allocate_cents,
    _allocate_mixed,
    _forwarder_tolerance,
    _hs_fields,
    _issue,
    _remarks_from,
    _two_decimals,
    amount_to_english_words,
    apply_overrides,
    build_customs_data,
    build_customs_from_tickets,
    consistency_checks,
    customs_filename,
    declare_mode_for,
    price_checks,
    suggest_order_no,
)

