"""发票数据装配：Step1/2 权威 → Step4 → 产品库 → 留空。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from fba_tool.invoice_table import (
    InvoiceLineItem,
    _catalog_record,
    _pcs_from_sku,
    extract_csv_sku_meta,
)
from fba_tool.master_db import get_product_by_sku
from fba_tool.sku_keys import lookup_sku, lookup_sku_detail, matching_texts, sku_key as _norm_key, sku_text
from fba_tool.product_catalog import ProductCatalog
from fba_tool.shipment_parser import CsvShipment


@dataclass
class WorkflowSkuContext:
    sku: str
    per_box: Optional[float] = None
    unit_kg: Optional[float] = None
    length_cm: Optional[float] = None
    width_cm: Optional[float] = None
    height_cm: Optional[float] = None
    box_seq: str = ""
    unit_weight_kg: Optional[float] = None
    length_cm_fwd: Optional[float] = None
    width_cm_fwd: Optional[float] = None
    height_cm_fwd: Optional[float] = None


@dataclass
class WorkflowFillBundle:
    by_sku: Dict[str, WorkflowSkuContext] = field(default_factory=dict)


def _to_float(val: Any) -> Optional[float]:
    if val in (None, ""):
        return None
    try:
        n = float(val)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _norm_sku(val: Any) -> str:
    return str(val or "").strip()


def _sku_key(val: Any) -> str:
    """S9-step4-fix3：by_sku 的键用原样写法（只去首尾空白），不再转大写；查找用 lookup_sku。"""
    return sku_text(val)


def _editor_sku(row: dict) -> str:
    return sku_text(row.get("SKU简称") or row.get("sku"))


def _box_seq_display(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    return text.replace(",", "-").replace("~", "-")


def _boxes_from_editor(box_editor: List[dict], sku: str) -> List[int]:
    boxes: List[int] = []
    keys = set(matching_texts(sku, (_editor_sku(r) for r in box_editor)))
    for row in box_editor:
        if _editor_sku(row) not in keys:
            continue
        try:
            boxes.append(int(row.get("箱号") or row.get("box_no") or 0))
        except (TypeError, ValueError):
            continue
    return sorted({b for b in boxes if b > 0})


def _qty_per_box_from_editor(box_editor: List[dict], sku: str) -> Optional[float]:
    keys = set(matching_texts(sku, (_editor_sku(r) for r in box_editor)))
    qtys: List[float] = []
    for row in box_editor:
        if _editor_sku(row) not in keys:
            continue
        q = _to_float(row.get("数量") or row.get("qty"))
        if q:
            qtys.append(q)
    if not qtys:
        return None
    return round(sum(qtys) / len(qtys), 2)


def build_workflow_bundle(workflow_json: dict | None) -> WorkflowFillBundle:
    bundle = WorkflowFillBundle()
    if not workflow_json:
        return bundle

    for row in workflow_json.get("input_rows") or workflow_json.get("step1_rows") or []:
        sku = _norm_sku(row.get("sku") or row.get("SKU简称"))
        if not sku:
            continue
        ctx = bundle.by_sku.setdefault(_sku_key(sku), WorkflowSkuContext(sku=sku))
        ctx.per_box = _to_float(row.get("perBox") or row.get("单箱装量")) or ctx.per_box
        ctx.unit_kg = _to_float(row.get("unitKg") or row.get("单个重量(kg)")) or ctx.unit_kg
        ctx.length_cm = _to_float(row.get("l") or row.get("箱长(cm)")) or ctx.length_cm
        ctx.width_cm = _to_float(row.get("w") or row.get("箱宽(cm)")) or ctx.width_cm
        ctx.height_cm = _to_float(row.get("h") or row.get("箱高(cm)")) or ctx.height_cm

    box_editor = workflow_json.get("box_editor") or workflow_json.get("step2_box_editor") or []
    for sku_key, ctx in list(bundle.by_sku.items()):
        if ctx.per_box is None:
            ctx.per_box = _qty_per_box_from_editor(box_editor, ctx.sku)

    for row in workflow_json.get("forwarder") or workflow_json.get("step4_forwarder") or []:
        if str(row.get("仓库代码", "")).startswith("—"):
            continue
        sku = _norm_sku(row.get("SKU") or row.get("sku"))
        if not sku:
            continue
        # 货代行和 Step1 行写法可能只差大小写：原样优先，否则唯一规范命中就并到那一条；多个候选时单独一条，不任选
        hit, how, _ = lookup_sku_detail(bundle.by_sku, sku)
        ctx = hit if how in ("exact", "normalized") else bundle.by_sku.setdefault(_sku_key(sku), WorkflowSkuContext(sku=sku))
        seq = str(row.get("箱序号") or "").strip()
        if seq:
            ctx.box_seq = _box_seq_display(seq)
        ctx.unit_weight_kg = _to_float(row.get("单件实重(kg)")) or ctx.unit_weight_kg
        ctx.length_cm_fwd = _to_float(row.get("箱子长(cm)")) or ctx.length_cm_fwd
        ctx.width_cm_fwd = _to_float(row.get("箱子宽(cm)")) or ctx.width_cm_fwd
        ctx.height_cm_fwd = _to_float(row.get("箱子高(cm)")) or ctx.height_cm_fwd

    return bundle


def _pick_source(
    step12_val: Any,
    step4_val: Any,
    catalog_val: Any,
    master_val: Any = None,
) -> Tuple[Any, str]:
    if step12_val not in (None, ""):
        return step12_val, "green"
    if step4_val not in (None, ""):
        return step4_val, "green"
    if catalog_val not in (None, ""):
        return catalog_val, "blue"
    if master_val not in (None, ""):
        return master_val, "blue"
    return "", "red"


def _master_float(master: Optional[dict], *keys: str) -> Optional[float]:
    if not master:
        return None
    for key in keys:
        val = _to_float(master.get(key))
        if val:
            return val
    return None


def _master_text(master: Optional[dict], *keys: str) -> str:
    if not master:
        return ""
    for key in keys:
        val = str(master.get(key) or "").strip()
        if val:
            return val
    return ""


def _format_box_range_hyphen(boxes: List[int]) -> str:
    if not boxes:
        return ""
    boxes = sorted(set(boxes))
    if len(boxes) == 1:
        return str(boxes[0])
    return f"{boxes[0]}-{boxes[-1]}"


def build_invoice_line_items_workflow(
    ship: CsvShipment,
    csv_bytes: bytes,
    catalog: Optional[ProductCatalog],
    workflow_json: dict | None,
    *,
    po_number: str = "",
    separate_material_purpose: bool = False,
) -> List[InvoiceLineItem]:
    """按 Step1/2 → Step4 → 产品库 → 留空 装配发票行（不含 DeepSeek）。"""
    if ship.box_items.empty:
        return []

    bundle = build_workflow_bundle(workflow_json)
    sku_meta = extract_csv_sku_meta(csv_bytes)
    po_text = str(po_number or "").strip()
    items: List[InvoiceLineItem] = []

    grouped = ship.box_items.groupby("SKU", sort=True)
    for sku, grp in grouped:
        sku_str = str(sku)
        rec = _catalog_record(catalog, sku_str)
        wf = lookup_sku(bundle.by_sku, sku_str)
        boxes = sorted(int(b) for b in grp["箱号"].tolist())

        spec_rows = (
            ship.box_specs[ship.box_specs["箱号"].isin(boxes)]
            if not ship.box_specs.empty
            else pd.DataFrame()
        )
        length = width = height = weight = 0.0
        if not spec_rows.empty:
            length = float(spec_rows["长(cm)"].median()) if "长(cm)" in spec_rows else 0
            width = float(spec_rows["宽(cm)"].median()) if "宽(cm)" in spec_rows else 0
            height = float(spec_rows["高(cm)"].median()) if "高(cm)" in spec_rows else 0
            weight = float(spec_rows["实重(kg)"].median()) if "实重(kg)" in spec_rows else 0

        csv_row = lookup_sku(sku_meta, sku_str, {})
        master = get_product_by_sku(sku_str)

        step12_box_range = ""
        if wf and wf.box_seq:
            step12_box_range = wf.box_seq
        elif wf:
            editor_boxes = _boxes_from_editor(
                (workflow_json or {}).get("box_editor") or [],
                sku_str,
            )
            if editor_boxes:
                step12_box_range = _format_box_range_hyphen(editor_boxes)
        step4_box_range = _format_box_range_hyphen(boxes)

        box_range_val, box_range_src = _pick_source(step12_box_range, step4_box_range, "")

        from fba_tool.invoice_rules import invoice_english_name

        catalog_english = _master_text(master, "english_name")
        english_val = invoice_english_name(catalog_english, csv_row.get("title", ""))
        english_src = "blue" if catalog_english else ("green" if english_val else "red")

        chinese_val, chinese_src = _pick_source(
            "",
            "",
            "",
            _master_text(master, "chinese_name", "model_name"),
        )

        qty_step12 = wf.per_box if wf and wf.per_box else None
        qty_step4 = None
        if not grp.empty:
            per_box_qty = grp.groupby("箱号")["数量"].sum()
            if not per_box_qty.empty:
                qty_step4 = round(float(per_box_qty.median()), 2)
        qty_master = _master_float(master, "qty_per_box")
        qty_val, qty_src = _pick_source(qty_step12, qty_step4, "", qty_master)

        from fba_tool.product_fields import resolve_declared_price

        resolved_price, _price_src = resolve_declared_price(master) if master else (None, "")
        declared_val, declared_src = (resolved_price, "blue") if resolved_price not in (None, "") else ("", "red")

        material_val, material_src = _pick_source("", "", "", _master_text(master, "material"))
        purpose_val, purpose_src = _pick_source("", "", "", _master_text(master, "purpose"))

        brand_val, brand_src = _pick_source("", "", "", _master_text(master, "brand"))
        hs_val, hs_src = _pick_source("", "", "", _master_text(master, "hs_code"))

        model_val, model_src = _pick_source("", "", "", _master_text(master, "model_name"))

        unit_w_step12 = wf.unit_kg if wf and wf.unit_kg else None
        unit_w_step4 = None
        total_qty = int(grp["数量"].sum())
        box_count = len(boxes)
        if weight and box_count and total_qty > 0:
            unit_w_step4 = round((weight * box_count) / total_qty, 3)
        unit_w_fwd = wf.unit_weight_kg if wf else None
        unit_weight_val, unit_weight_src = _pick_source(
            unit_w_step12 or unit_w_fwd,
            unit_w_step4,
            "",
            _master_float(master, "unit_weight", "carton_weight"),
        )

        len_step12 = wf.length_cm if wf else None
        len_step4 = length if length else None
        len_fwd = wf.length_cm_fwd if wf else None
        length_val, length_src = _pick_source(
            len_step12 or len_fwd,
            len_step4,
            "",
            _master_float(master, "unit_length", "carton_length"),
        )

        wid_step12 = wf.width_cm if wf else None
        wid_step4 = width if width else None
        wid_fwd = wf.width_cm_fwd if wf else None
        width_val, width_src = _pick_source(
            wid_step12 or wid_fwd,
            wid_step4,
            "",
            _master_float(master, "unit_width", "carton_width"),
        )

        ht_step12 = wf.height_cm if wf else None
        ht_step4 = height if height else None
        ht_fwd = wf.height_cm_fwd if wf else None
        height_val, height_src = _pick_source(
            ht_step12 or ht_fwd,
            ht_step4,
            "",
            _master_float(master, "unit_height", "carton_height"),
        )

        material_display = material_val
        if not separate_material_purpose and purpose_val:
            if material_display and purpose_val not in material_display:
                material_display = f"{material_display}/{purpose_val}"
            elif not material_display:
                material_display = purpose_val

        purchase = rec.unit_cost if rec and rec.unit_cost else None
        pcs = _pcs_from_sku(sku_str)
        asin = csv_row.get("asin") or (master.get("asin") if master else "") or (rec.asin if rec else "")

        total_declared_value_usd = ""
        if declared_val not in (None, "") and total_qty > 0:
            try:
                total_declared_value_usd = round(float(declared_val) * total_qty, 2)
            except (TypeError, ValueError):
                pass

        values = {
            "shipment_id": ship.shipment_id,
            "fba_id": ship.shipment_id,
            "reference_id": "",
            "po_number": po_text,
            "box_range": box_range_val,
            "box_count": box_count,
            "sku": sku_str,
            "english_name": english_val,
            "chinese_name": chinese_val,
            "brand": brand_val,
            "material": material_display if not separate_material_purpose else material_val,
            "purpose": purpose_val,
            "hs_code": hs_val,
            "asin": asin,
            "battery": "否",
            "magnet": "否",
            "model": model_val,
            "total_qty": total_qty,
            "qty_per_box": qty_val,
            "unit": "套",
            "pcs_per_set": pcs if pcs else "",
            "purchase_price": purchase if purchase else "",
            "declared_price": declared_val if declared_val != "" else "",
            "total_declared_value_usd": total_declared_value_usd,
            "unit_weight_kg": unit_weight_val if unit_weight_val != "" else "",
            "sku_image": "",
            "shipping_mark": ship.warehouse_code or "",
            "box_weight": round(weight, 2) if weight else "",
            "length": length_val if length_val != "" else "",
            "width": width_val if width_val != "" else "",
            "height": height_val if height_val != "" else "",
        }

        sources = {
            "box_range": box_range_src,
            "fba_id": "green",
            "po_number": "green" if po_text else "red",
            "english_name": english_src,
            "chinese_name": chinese_src,
            "qty_per_box": qty_src,
            "declared_price": declared_src,
            "material": material_src,
            "purpose": purpose_src,
            "brand": brand_src,
            "hs_code": hs_src,
            "model": model_src,
            "unit_weight_kg": unit_weight_src,
            "length": length_src,
            "width": width_src,
            "height": height_src,
            "shipment_id": "green",
            "sku": "green",
            "total_qty": "green",
            "box_count": "green",
            "battery": "green",
            "magnet": "green",
            "unit": "green",
            "shipping_mark": "green",
        }
        for key, val in values.items():
            if key in sources:
                continue
            sources[key] = "red" if val in (None, "") else "green"

        items.append(InvoiceLineItem(values=values, sources=sources))

    fallback_hs = next((it.values.get("hs_code") for it in items if it.values.get("hs_code")), "")
    if fallback_hs:
        for item in items:
            if not item.values.get("hs_code"):
                item.values["hs_code"] = fallback_hs
                item.sources["hs_code"] = "blue"

    return items
