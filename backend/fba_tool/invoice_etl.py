"""Step 4.5 发票 ETL 五段流水线（配置驱动，替代硬编码 SKU 聚合）。"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from fba_tool.forwarder_mapping import get_forwarder_mapping, normalize_group_logic
from fba_tool.invoice_table import InvoiceLineItem, extract_csv_sku_meta
from fba_tool.invoice_workflow_fill import build_workflow_bundle
from fba_tool.master_db import get_product_by_sku
from fba_tool.sku_keys import lookup_sku, sku_key as _norm_key
from fba_tool.product_catalog import ProductCatalog
from fba_tool.shipment_parser import CsvShipment

LBS_TO_KG = 0.45359237
IN_TO_CM = 2.54


def _model_text(val: Any) -> str:
    """型号列只接受 model_name。空值保持空白，不用 SKU 顶上。"""
    if val is None:
        return ""
    try:
        if pd.isna(val):
            return ""
    except TypeError:
        pass
    text = str(val).strip()
    return "" if text.lower() == "nan" else text


def _to_float(val: Any) -> Optional[float]:
    if val in (None, ""):
        return None
    try:
        n = float(val)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _pick_source(step12: Any, step4: Any, catalog: Any) -> Tuple[Any, str]:
    if step12 not in (None, ""):
        return step12, "green"
    if step4 not in (None, ""):
        return step4, "green"
    if catalog not in (None, ""):
        return catalog, "blue"
    return "", "red"


def _format_box_range(boxes: List[int], separator: str = "-") -> str:
    if not boxes:
        return ""
    boxes = sorted(set(int(b) for b in boxes))
    if len(boxes) == 1:
        return str(boxes[0])
    return f"{boxes[0]}{separator}{boxes[-1]}"


def _consecutive_runs(box_ids: List[int]) -> List[Tuple[int, int]]:
    if not box_ids:
        return []
    sorted_ids = sorted(set(int(b) for b in box_ids))
    runs: List[Tuple[int, int]] = []
    start = prev = sorted_ids[0]
    for box_id in sorted_ids[1:]:
        if box_id == prev + 1:
            prev = box_id
        else:
            runs.append((start, prev))
            start = prev = box_id
    runs.append((start, prev))
    return runs


def extract_unpivot(ship: CsvShipment) -> pd.DataFrame:
    """Step 1: 箱-SKU 长表。"""
    items = ship.box_items.copy()
    if items.empty:
        return pd.DataFrame(
            columns=[
                "shipment_id",
                "warehouse_code",
                "box_id",
                "sku",
                "qty",
                "fba_box_id",
            ],
        )

    items = items.rename(columns={"箱号": "box_id", "SKU": "sku", "数量": "qty"})
    items["shipment_id"] = ship.shipment_id
    items["warehouse_code"] = ship.warehouse_code
    items["fba_box_id"] = items["box_id"].map(lambda b: ship.box_fba_ids.get(int(b), ""))

    if not ship.box_specs.empty:
        specs = ship.box_specs.copy()
        if "箱号" in specs.columns:
            specs = specs.rename(columns={"箱号": "box_id"})
            items = items.merge(specs, on="box_id", how="left", suffixes=("", "_spec"))
    return items


def join_master_db(df: pd.DataFrame, warnings: List[str]) -> pd.DataFrame:
    """Step 2: 左连接主库字段。"""
    if df.empty:
        return df

    master_cols = [
        "master_chinese_name",
        "master_english_name",
        "master_hs_code",
        "master_brand",
        "master_material",
        "master_purpose",
        "master_declared_price",
        "master_length_cm",
        "master_width_cm",
        "master_height_cm",
        "master_unit_kg",
        "master_asin",
        "master_model",
    ]
    for col in master_cols:
        df[col] = None

    missing_skus: set[str] = set()
    for idx, row in df.iterrows():
        sku = str(row.get("sku") or "").strip()
        if not sku:
            continue
        master = get_product_by_sku(sku)
        if not master:
            missing_skus.add(sku)
            continue
        df.at[idx, "master_chinese_name"] = master.get("chinese_name") or ""
        df.at[idx, "master_english_name"] = master.get("english_name") or ""
        df.at[idx, "master_hs_code"] = master.get("hs_code") or ""
        df.at[idx, "master_brand"] = master.get("brand") or ""
        df.at[idx, "master_material"] = master.get("material") or ""
        df.at[idx, "master_purpose"] = master.get("purpose") or ""
        df.at[idx, "master_declared_price"] = _to_float(master.get("declared_value"))
        df.at[idx, "master_length_cm"] = _to_float(
            master.get("carton_length") or master.get("unit_length")
        )
        df.at[idx, "master_width_cm"] = _to_float(
            master.get("carton_width") or master.get("unit_width")
        )
        df.at[idx, "master_height_cm"] = _to_float(
            master.get("carton_height") or master.get("unit_height")
        )
        df.at[idx, "master_unit_kg"] = _to_float(
            master.get("carton_weight") or master.get("unit_weight")
        )
        df.at[idx, "master_asin"] = master.get("asin") or ""
        df.at[idx, "master_model"] = master.get("model_name") or ""

    for sku in sorted(missing_skus):
        warnings.append(f"主数据缺少 SKU：{sku}")

    return df


def priority_fallback(
    df: pd.DataFrame,
    workflow_json: dict | None,
    csv_bytes: bytes,
    catalog: Optional[ProductCatalog] = None,
) -> pd.DataFrame:
    """Step 3: Step1/2 → Step4 → SQLite 主库兜底（catalog 参数保留兼容，不再使用）。"""
    if df.empty:
        return df

    bundle = build_workflow_bundle(workflow_json)
    sku_meta = extract_csv_sku_meta(csv_bytes)

    for idx, row in df.iterrows():
        sku = str(row.get("sku") or "")
        wf = bundle.by_sku.get(_norm_key(sku))  # S9-step3：统一大小写 / 全角规则

        length_step4 = _to_float(row.get("长(cm)"))
        width_step4 = _to_float(row.get("宽(cm)"))
        height_step4 = _to_float(row.get("高(cm)"))
        weight_step4 = _to_float(row.get("实重(kg)"))

        from fba_tool.invoice_rules import invoice_english_name

        title = lookup_sku(sku_meta, sku, {}).get("title", "")
        df.at[idx, "english_name"] = invoice_english_name(row.get("master_english_name"), title)
        df.at[idx, "chinese_name"], _ = _pick_source("", "", row.get("master_chinese_name"))
        df.at[idx, "hs_code"], _ = _pick_source("", "", row.get("master_hs_code"))
        df.at[idx, "brand"], _ = _pick_source("", "", row.get("master_brand"))
        df.at[idx, "material"], _ = _pick_source("", "", row.get("master_material"))
        df.at[idx, "purpose"], _ = _pick_source("", "", row.get("master_purpose"))
        df.at[idx, "declared_price"], _ = _pick_source("", "", row.get("master_declared_price"))

        qty_step4 = _to_float(row.get("qty"))
        qty_step12 = wf.per_box if wf else None
        df.at[idx, "qty_per_box"], _ = _pick_source(qty_step12, qty_step4, "")

        len_s12 = wf.length_cm if wf else None
        len_fwd = wf.length_cm_fwd if wf else None
        df.at[idx, "length_cm"], _ = _pick_source(
            len_s12 or len_fwd,
            length_step4,
            row.get("master_length_cm"),
        )
        wid_s12 = wf.width_cm if wf else None
        wid_fwd = wf.width_cm_fwd if wf else None
        df.at[idx, "width_cm"], _ = _pick_source(
            wid_s12 or wid_fwd,
            width_step4,
            row.get("master_width_cm"),
        )
        ht_s12 = wf.height_cm if wf else None
        ht_fwd = wf.height_cm_fwd if wf else None
        df.at[idx, "height_cm"], _ = _pick_source(
            ht_s12 or ht_fwd,
            height_step4,
            row.get("master_height_cm"),
        )

        unit_w_step12 = wf.unit_kg if wf else None
        unit_w_fwd = wf.unit_weight_kg if wf else None
        unit_w_step4 = None
        if weight_step4 and qty_step4:
            unit_w_step4 = round(weight_step4 / qty_step4, 3)
        df.at[idx, "unit_weight_kg"], _ = _pick_source(
            unit_w_step12 or unit_w_fwd,
            unit_w_step4,
            row.get("master_unit_kg"),
        )
        df.at[idx, "model"] = str(row.get("master_model") or "").strip()
        df.at[idx, "box_weight_kg"] = weight_step4

    return df


def apply_unit_conversion(df: pd.DataFrame, unit_cfg: Dict[str, str]) -> pd.DataFrame:
    """Step 4: 按 mapping 做 lbs/in → kg/cm。"""
    if df.empty:
        return df
    weight_unit = str(unit_cfg.get("weight") or "kg").lower()
    dim_unit = str(unit_cfg.get("dimension") or "cm").lower()

    if weight_unit == "kg":
        for col in ("unit_weight_kg", "box_weight_kg", "实重(kg)"):
            if col in df.columns:
                lbs_col = f"{col}_lbs"
                if lbs_col in df.columns:
                    df[col] = df[col].fillna(df[lbs_col] * LBS_TO_KG)

    if dim_unit == "cm":
        for col in ("length_cm", "width_cm", "height_cm", "长(cm)", "宽(cm)", "高(cm)"):
            if col in df.columns:
                in_col = col.replace("(cm)", "_in")
                if in_col in df.columns:
                    df[col] = df[col].fillna(df[in_col] * IN_TO_CM)
    return df


def group_by_logic(df: pd.DataFrame, group_logic: str) -> pd.DataFrame:
    """Step 5: 按配置合并行。"""
    if df.empty:
        return df

    logic = normalize_group_logic(group_logic)
    if logic == "GROUP_BY_BOX_RANGE":
        return _group_by_box_range(df)
    if logic == "GROUP_BY_SKU":
        return _group_by_sku(df)
    return _group_detail_rows(df)


def _group_by_sku(df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for _sku, grp in df.groupby("sku", sort=True):
        boxes = sorted(int(b) for b in grp["box_id"].tolist())
        row = grp.iloc[0].to_dict()
        row["box_range"] = _format_box_range(boxes)
        row["box_count"] = len(set(boxes))
        row["total_qty"] = int(grp["qty"].sum())
        rows.append(row)
    return pd.DataFrame(rows)


def _group_detail_rows(df: pd.DataFrame) -> pd.DataFrame:
    """DETAIL_ROW：不合并，每箱一行。"""
    rows: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        d = row.to_dict()
        box_id = int(d.get("box_id") or 0)
        d["box_range"] = str(box_id) if box_id else ""
        d["box_count"] = 1
        d["total_qty"] = int(d.get("qty") or 0)
        rows.append(d)
    return pd.DataFrame(rows)


def _resolve_box_num(series: pd.Series) -> pd.Series:
    """将箱号转为连续判断用的整数：优先纯数字，否则取末尾数字（如 FBA...U000005 → 5）。"""
    as_str = series.astype(str).str.strip()
    numeric = pd.to_numeric(as_str, errors="coerce")
    tail = pd.to_numeric(as_str.str.extract(r"(\d+)$", expand=False), errors="coerce")
    return numeric.fillna(tail).fillna(0).astype(int)


def _group_by_box_range(df: pd.DataFrame) -> pd.DataFrame:
    """按 FBAID + SKU + 型号 + 单箱量 + 尺寸分组，并在组内合并连续箱号（如 1-5）。

    型号相同、单箱量和尺寸也相同的两个 SKU 仍各占一行。空型号不写进型号列。
    """
    if df.empty:
        return df

    work = df.copy()
    work["_box_num"] = _resolve_box_num(work["box_id"])
    work = work[work["_box_num"] > 0].copy()
    if work.empty:
        return df.iloc[0:0].copy()

    work["fba_id"] = work["shipment_id"].astype(str).str.strip()
    if "sku" not in work.columns:
        work["sku"] = ""
    work["sku"] = work["sku"].fillna("").astype(str).str.strip()
    if "model" not in work.columns:
        work["model"] = ""
    work["model"] = work["model"].fillna("").astype(str).str.strip().replace({"nan": ""})
    work["_model_group"] = work["model"].where(work["model"] != "", work["sku"])
    work["_gk_qty"] = work["qty_per_box"].map(lambda v: round(_to_float(v) or 0, 3))
    work["_gk_len"] = work["length_cm"].map(lambda v: round(_to_float(v) or 0, 3))
    work["_gk_wid"] = work["width_cm"].map(lambda v: round(_to_float(v) or 0, 3))
    work["_gk_hei"] = work["height_cm"].map(lambda v: round(_to_float(v) or 0, 3))

    group_keys = ["fba_id", "sku", "_model_group", "_gk_qty", "_gk_len", "_gk_wid", "_gk_hei"]
    work = work.sort_values(group_keys + ["_box_num"], kind="mergesort")

    prev_box = work.groupby(group_keys, sort=False)["_box_num"].shift(1)
    key_changed = work[group_keys].ne(work.groupby(group_keys, sort=False)[group_keys].shift(1)).any(axis=1)
    work["_block"] = prev_box.isna() | key_changed | (work["_box_num"] != prev_box + 1)
    work["_block"] = work.groupby(group_keys, sort=False)["_block"].cumsum().astype(int)

    rows: List[Dict[str, Any]] = []
    for _keys, grp in work.groupby(group_keys + ["_block"], sort=True):
        box_nums = sorted(int(b) for b in grp["_box_num"].tolist())
        row = grp.iloc[0].to_dict()
        row["box_id"] = box_nums[0]
        row["box_range"] = _format_box_range(box_nums)
        row["box_count"] = len(box_nums)
        row["total_qty"] = int(grp["qty"].sum())
        row["fba_id"] = row.get("fba_id") or row.get("shipment_id") or ""
        fba_box_ids = [str(x) for x in grp["fba_box_id"].tolist() if str(x or "").strip()]
        if fba_box_ids:
            row["fba_id_range"] = (
                f"{fba_box_ids[0]} - {fba_box_ids[-1]}" if len(fba_box_ids) > 1 else fba_box_ids[0]
            )
        rows.append(row)

    out = pd.DataFrame(rows)
    drop_cols = [c for c in ("_gk_qty", "_gk_len", "_gk_wid", "_gk_hei", "_block", "_box_num", "_model_group") if c in out.columns]
    if drop_cols:
        out = out.drop(columns=drop_cols)
    return out


def dataframe_to_line_items(
    df: pd.DataFrame,
    ship: CsvShipment,
    *,
    po_number: str = "",
    separate_material_purpose: bool = False,
) -> List[InvoiceLineItem]:
    items: List[InvoiceLineItem] = []
    po_text = str(po_number or "").strip()

    for _, row in df.iterrows():
        material = str(row.get("material") or "")
        purpose = str(row.get("purpose") or "")
        if not separate_material_purpose and purpose:
            if material and purpose not in material:
                material = f"{material}/{purpose}"
            elif not material:
                material = purpose

        declared = row.get("declared_price")
        total_qty = int(row.get("total_qty") or row.get("qty") or 0)
        total_declared = ""
        if declared not in (None, "") and total_qty > 0:
            try:
                total_declared = round(float(declared) * total_qty, 2)
            except (TypeError, ValueError):
                pass

        values = {
            "shipment_id": ship.shipment_id,
            "fba_id": row.get("fba_id") or row.get("fba_id_range") or ship.shipment_id,
            "reference_id": "",
            "po_number": po_text,
            "box_range": row.get("box_range") or "",
            "box_count": row.get("box_count") or 0,
            "sku": str(row.get("sku") or ""),
            "english_name": row.get("english_name") or "",
            "chinese_name": row.get("chinese_name") or "",
            "brand": row.get("brand") or "",
            "material": material,
            "purpose": purpose,
            "hs_code": row.get("hs_code") or "",
            "asin": row.get("master_asin") or "",
            "battery": "否",
            "magnet": "否",
            "model": _model_text(row.get("model")),
            "total_qty": total_qty,
            "qty_per_box": row.get("qty_per_box") or "",
            "unit": "套",
            "pcs_per_set": "",
            "purchase_price": "",
            "declared_price": declared if declared not in (None, "") else "",
            "total_declared_value_usd": total_declared,
            "unit_weight_kg": row.get("unit_weight_kg") or "",
            "sku_image": "",
            "shipping_mark": ship.warehouse_code or "",
            "box_weight": row.get("box_weight_kg") or "",
            "length": row.get("length_cm") or "",
            "width": row.get("width_cm") or "",
            "height": row.get("height_cm") or "",
        }

        sources: Dict[str, str] = {}
        for key, val in values.items():
            if val in (None, ""):
                sources[key] = "red" if key in ("po_number", "chinese_name", "hs_code", "declared_price") else "red"
            elif key in ("shipment_id", "fba_id", "box_range", "box_count", "total_qty", "sku"):
                sources[key] = "green"
            elif key in ("english_name", "qty_per_box", "length", "width", "height", "unit_weight_kg"):
                sources[key] = "green"
            elif key in ("chinese_name", "brand", "material", "purpose", "hs_code", "declared_price"):
                sources[key] = "blue" if val else "red"
            else:
                sources[key] = "green" if val else "red"
        if po_text:
            sources["po_number"] = "green"

        items.append(InvoiceLineItem(values=values, sources=sources))

    fallback_hs = next((it.values.get("hs_code") for it in items if it.values.get("hs_code")), "")
    if fallback_hs:
        for item in items:
            if not item.values.get("hs_code"):
                item.values["hs_code"] = fallback_hs
                item.sources["hs_code"] = "blue"

    return items


def run_invoice_etl(
    *,
    forwarder_id: str,
    ship: CsvShipment,
    csv_bytes: bytes,
    workflow_json: dict | None,
    po_number: str = "",
    catalog: Optional[ProductCatalog] = None,
    separate_material_purpose: bool | None = None,
) -> Tuple[List[InvoiceLineItem], List[str]]:
    """执行完整五段 ETL，返回发票行与 warnings。"""
    warnings: List[str] = []
    mapping = get_forwarder_mapping(forwarder_id) or {}
    group_logic = normalize_group_logic(mapping.get("group_logic"))
    unit_cfg = mapping.get("unit_conversion") or {}
    if separate_material_purpose is None:
        separate_mp = bool(mapping.get("separate_material_purpose"))
    else:
        separate_mp = bool(separate_material_purpose)

    df = extract_unpivot(ship)
    if df.empty:
        warnings.append("货件无箱内 SKU 数据")
        return [], warnings

    df = join_master_db(df, warnings)
    df = priority_fallback(df, workflow_json, csv_bytes, catalog)
    df = apply_unit_conversion(df, unit_cfg)
    grouped = group_by_logic(df, group_logic)
    line_items = dataframe_to_line_items(
        grouped,
        ship,
        po_number=po_number,
        separate_material_purpose=separate_mp,
    )
    return line_items, warnings
