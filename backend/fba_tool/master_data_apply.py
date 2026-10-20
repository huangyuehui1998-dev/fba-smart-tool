"""主数据应用：单品尺寸 vs 外箱尺寸逻辑分离。"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pandas as pd

from fba_tool.master_db import get_product_by_sku, get_products_by_skus

CARTON_DIM_KEYS = ("carton_length", "carton_width", "carton_height")
UNIT_DIM_KEYS = ("unit_length", "unit_width", "unit_height")


def apply_master_to_input_rows(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """合并主数据到 Step1 行。

    - FNSKU：来自主库（有值才写）
    - 外箱尺寸 / 单箱装量：仅当本票该格为空时补全（校验补充），已填不覆盖
    - 发货总数永不从主库灌入
    """
    skus = [str(r.get("SKU简称") or "").strip() for r in rows]
    master_map = get_products_by_skus([s for s in skus if s])
    out: List[Dict[str, Any]] = []
    sources: List[str] = []
    for row in rows:
        sku = str(row.get("SKU简称") or "").strip()
        master = master_map.get(sku) or (get_product_by_sku(sku) if sku else None)
        new_row = dict(row)
        if master:
            if master.get("fnsku"):
                new_row["FNSKU"] = master["fnsku"]
            user_had_carton = not all(_is_empty_num(row.get(col)) for col in ("箱长(cm)", "箱宽(cm)", "箱高(cm)"))
            if _has_carton_dims(master):
                if _is_empty_num(new_row.get("箱长(cm)")):
                    new_row["箱长(cm)"] = master["carton_length"]
                if _is_empty_num(new_row.get("箱宽(cm)")):
                    new_row["箱宽(cm)"] = master["carton_width"]
                if _is_empty_num(new_row.get("箱高(cm)")):
                    new_row["箱高(cm)"] = master["carton_height"]
            if _is_empty_num(new_row.get("单箱装量")) and float(master.get("qty_per_box") or 0) > 0:
                new_row["单箱装量"] = master["qty_per_box"]
            # 单箱重（含箱）只在本票装量与产品库箱规一致时补，避免尾箱/改装量时套错重量
            if (
                _is_empty_num(new_row.get("单箱毛重(kg)"))
                and float(master.get("carton_gross_weight") or 0) > 0
                and float(master.get("qty_per_box") or 0) > 0
                and not _is_empty_num(new_row.get("单箱装量"))
                and float(new_row["单箱装量"]) == float(master["qty_per_box"])
            ):
                new_row["单箱毛重(kg)"] = master["carton_gross_weight"]
            filled_carton = not all(_is_empty_num(new_row.get(col)) for col in ("箱长(cm)", "箱宽(cm)", "箱高(cm)"))
            if filled_carton and not user_had_carton and _has_carton_dims(master):
                sources.append("official")
            else:
                sources.append("manual")
        else:
            sources.append("manual")
        out.append(new_row)
    return out, sources


def build_placement_unit_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """为入库配置费构建「单品」维度输入，与 Step1 外箱录入完全分离。"""
    skus = [str(r.get("SKU简称") or "").strip() for r in rows if str(r.get("SKU简称") or "").strip()]
    master_map = get_products_by_skus(skus)
    placement_rows: List[Dict[str, Any]] = []

    for row in rows:
        sku = str(row.get("SKU简称") or "").strip()
        if not sku:
            continue
        qty = _to_int(row.get("发货总数"))
        if qty <= 0:
            continue

        master = master_map.get(sku) or get_product_by_sku(sku)
        unit_l = unit_w = unit_h = 0.0
        unit_wt = 0.0
        dims_source = "none"

        if master and _has_unit_dims(master):
            unit_l = float(master["unit_length"] or 0)
            unit_w = float(master["unit_width"] or 0)
            unit_h = float(master["unit_height"] or 0)
            unit_wt = float(master.get("unit_weight") or 0)
            dims_source = "fee_preview"
        elif master and float(master.get("unit_weight") or 0) > 0:
            unit_wt = float(master["unit_weight"])
            dims_source = "fee_preview_weight_only"
        else:
            unit_wt = _to_float(row.get("单个重量(kg)"))
            dims_source = "manual_weight_only"

        placement_rows.append(
            {
                "SKU简称": sku,
                "发货总数": qty,
                "unit_length_cm": unit_l,
                "unit_width_cm": unit_w,
                "unit_height_cm": unit_h,
                "unit_weight_kg": unit_wt,
                "unit_dims_source": dims_source,
            }
        )
    return placement_rows


def apply_master_to_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    rows, _ = apply_master_to_input_rows(df.to_dict(orient="records"))
    return pd.DataFrame(rows, columns=list(df.columns))


def resolve_sku_master_flags(skus: List[str]) -> Dict[str, str]:
    master_map = get_products_by_skus([s for s in skus if s])
    flags: Dict[str, str] = {}
    for sku in skus:
        key = str(sku or "").strip()
        if not key:
            continue
        master = master_map.get(key)
        flags[key] = "official" if master and _has_carton_dims(master) else "manual"
    return flags


def _has_carton_dims(master: Dict[str, Any]) -> bool:
    return all(float(master.get(k) or 0) > 0 for k in CARTON_DIM_KEYS)


def _has_unit_dims(master: Dict[str, Any]) -> bool:
    return all(float(master.get(k) or 0) > 0 for k in UNIT_DIM_KEYS)


def _is_empty_num(val: Any) -> bool:
    if val in (None, ""):
        return True
    try:
        return float(str(val).replace(",", "").strip() or 0) <= 0
    except (TypeError, ValueError):
        return True


def _to_int(val: Any) -> int:
    try:
        return int(float(str(val).replace(",", "").strip() or 0))
    except (TypeError, ValueError):
        return 0


def _to_float(val: Any) -> float:
    try:
        return float(str(val).replace(",", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0
