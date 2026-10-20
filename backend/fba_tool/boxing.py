from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

import pandas as pd

from fba_tool.box_weight import box_gross_kg, carrier_tare, mixed_box_would_exceed
from fba_tool.models import BoxItem, BoxPlan, SkuRow
from fba_tool.user_config import param, weight_limit_kg


def dataframe_to_sku_rows(df: pd.DataFrame) -> List[SkuRow]:
    rows: List[SkuRow] = []
    for _, r in df.iterrows():
        sku = str(r["SKU简称"]).strip()
        if not sku:
            continue
        rows.append(
            SkuRow(
                sku=sku,
                total_qty=int(r["发货总数"] or 0),
                carton_qty=int(r["单箱装量"] or 0),
                length_cm=float(r["箱长(cm)"] or 0),
                width_cm=float(r["箱宽(cm)"] or 0),
                height_cm=float(r["箱高(cm)"] or 0),
                unit_weight_kg=float(r.get("单个重量(kg)", 0) or 0),
                carton_tare_kg=float(r.get("空纸箱重(kg)", 0) or 0),
                carton_gross_kg=r.get("单箱毛重(kg)", None),
            )
        )
    return rows


def generate_box_plan(
    sku_rows: List[SkuRow],
    max_mixed_items: int | None = None,
    max_weight_kg: float | None = None,
) -> Tuple[List[BoxPlan], pd.DataFrame]:
    max_mixed_items = int(max_mixed_items or param("max_mixed_items_per_box", 40))
    max_weight_kg = float(max_weight_kg if max_weight_kg is not None else weight_limit_kg())
    plans: List[BoxPlan] = []
    tail_pool: List[Dict[str, float]] = []
    box_no = 1

    for sku in sku_rows:
        for _ in range(sku.full_cartons):
            plans.append(
                BoxPlan(box_no=box_no, items=[BoxItem(sku=sku.sku, qty=sku.carton_qty)], source="整箱")
            )
            box_no += 1
        if sku.remainder > 0:
            tail_pool.append(
                {
                    "SKU简称": sku.sku,
                    "剩余数量": sku.remainder,
                    "单个重量(kg)": sku.unit_weight_kg,
                    "单件体积(cm3)": sku.unit_volume_cm3(),
                }
            )

    # 动态选举混装“承载纸箱”
    global_carrier_volume = 0.0
    for sku in sku_rows:
        if sku.remainder > 0:
            vol = sku.length_cm * sku.width_cm * sku.height_cm
            if vol > global_carrier_volume:
                global_carrier_volume = vol
    
    if global_carrier_volume <= 0:
        global_carrier_volume = 60.0 * 40.0 * 40.0  # 默认混装箱规 60x40x40
        
    usable_volume = global_carrier_volume * 0.8  # 80% 空间利用率限制

    # 贪心混装（体积近似，不是 3D 摆放）
    # 单件体积 = 外箱体积 / 单箱装量，不是真实单品长宽高。
    # 因此默认不引入 py3dbp：用假立方体做 3D 会比贪心更像正确、实际更错。
    # 仅当 product_master 具备完整 unit_length/width/height 且 A/B 更优时再考虑 engine=3d。
    sku_map = {s.sku: s for s in sku_rows}
    tail_pool.sort(key=lambda x: x["单个重量(kg)"], reverse=True)
    max_sku_kinds = int(param("max_sku_kinds_per_box", max_mixed_items))
    current_items: List[BoxItem] = []
    current_weight = 0.0
    current_volume = 0.0
    current_count = 0

    def _flush() -> None:
        nonlocal box_no, current_items, current_weight, current_volume, current_count
        if not current_items:
            return
        plans.append(BoxPlan(box_no=box_no, items=current_items, source="混装"))
        box_no += 1
        current_items = []
        current_weight = 0.0
        current_volume = 0.0
        current_count = 0

    for tail in tail_pool:
        qty_left = int(tail["剩余数量"])
        unit_weight = float(tail["单个重量(kg)"] or 0)
        unit_vol = float(tail["单件体积(cm3)"] or 0)
        sku_name = str(tail["SKU简称"])
        while qty_left > 0:
            kinds = {item.sku for item in current_items}
            kind_full = sku_name not in kinds and len(kinds) >= max_sku_kinds
            room_count = max_mixed_items - current_count
            tare = carrier_tare([it.sku for it in current_items] + [sku_name], sku_map)
            room_weight = qty_left
            if unit_weight > 0:
                budget = max_weight_kg - tare - current_weight
                room_weight = int(budget / unit_weight) if budget > 0 else 0
            elif mixed_box_would_exceed(current_weight, 0, tare, max_weight_kg):
                room_weight = 0
            room_volume = qty_left
            if unit_vol > 0:
                room_volume = int((usable_volume - current_volume) / unit_vol)
            fit = min(qty_left, room_count, room_weight, room_volume)
            if kind_full or fit <= 0:
                if current_items:
                    _flush()
                    continue
                fit = 1
            current_items.append(BoxItem(sku=sku_name, qty=fit))
            current_weight += unit_weight * fit
            current_volume += unit_vol * fit
            current_count += fit
            qty_left -= fit
    _flush()

    return plans, pd.DataFrame(tail_pool)


def remainder_split_count(plans: List[BoxPlan]) -> int:
    """同一 SKU 的尾数被拆进几只混装箱。0 表示每个尾数 SKU 都只在一只混装箱里。"""
    seen: Dict[str, int] = defaultdict(int)
    for plan in plans:
        if plan.source != "混装":
            continue
        for sku in {item.sku for item in plan.items}:
            seen[sku] += 1
    return sum(count - 1 for count in seen.values() if count > 1)


def unit_over_limit_warnings(sku_rows: List[SkuRow], max_weight_kg: float | None = None) -> List[str]:
    limit = float(max_weight_kg if max_weight_kg is not None else weight_limit_kg())
    warnings: List[str] = []
    for sku in sku_rows:
        unit = float(sku.unit_weight_kg or 0)
        if unit > limit:
            warnings.append(f"{sku.sku} 单件重量 {unit:g} kg 超过上限 {limit:g} kg，排箱前请先拆件或改上限")
    return warnings


def calculate_boxes(sku_rows: List[SkuRow], max_mixed_items: int | None = None, max_weight_kg: float | None = None):
    """排箱并带上单件超重提示。返回 (plans, tail_df, warnings)。"""
    warnings = unit_over_limit_warnings(sku_rows, max_weight_kg)
    plans, tail_df = generate_box_plan(sku_rows, max_mixed_items=max_mixed_items, max_weight_kg=max_weight_kg)
    return plans, tail_df, warnings


def plans_to_editor_df(plans: List[BoxPlan]) -> pd.DataFrame:
    rows = []
    for p in plans:
        merged: Dict[str, int] = defaultdict(int)
        for it in p.items:
            merged[it.sku] += int(it.qty)
        for sku, qty in merged.items():
            rows.append({"箱号": p.box_no, "来源": p.source, "SKU简称": sku, "数量": qty})
    if not rows:
        return pd.DataFrame(columns=["箱号", "来源", "SKU简称", "数量"])
    return pd.DataFrame(rows).sort_values(["箱号", "SKU简称"]).reset_index(drop=True)


def box_metrics(editor_df: pd.DataFrame, sku_rows: List[SkuRow]) -> pd.DataFrame:
    sku_map = {s.sku: s for s in sku_rows}
    by_box = []
    for box_no, group in editor_df.groupby("箱号"):
        total_qty = int(group["数量"].sum())
        net_weight = 0.0
        max_box_vol = 0.0
        lines = []
        for _, row in group.iterrows():
            sku = sku_map.get(str(row["SKU简称"]))
            if not sku:
                continue
            qty = int(row["数量"])
            net_weight += sku.unit_weight_kg * qty
            lines.append((sku.sku, qty))
            vol = sku.length_cm * sku.width_cm * sku.height_cm
            if vol > max_box_vol:
                max_box_vol = vol

        gross_weight = box_gross_kg(lines, sku_map)

        is_mixed = len(group) > 1
        if not is_mixed and len(group) == 1:
            row = group.iloc[0]
            sku = sku_map.get(str(row["SKU简称"]))
            if sku and int(row["数量"]) != sku.carton_qty:
                is_mixed = True

        if is_mixed:
            volume = max_box_vol if max_box_vol > 0 else 60.0 * 40.0 * 40.0
        else:
            row = group.iloc[0]
            sku = sku_map.get(str(row["SKU简称"]))
            volume = (sku.length_cm * sku.width_cm * sku.height_cm) if sku else 0.0
        by_box.append(
            {
                "箱号": int(box_no),
                "SKU种类": group["SKU简称"].nunique(),
                "件数": total_qty,
                "净重(kg)": round(net_weight, 3),
                "毛重(kg)": round(gross_weight, 3),
                "体积(cm3)": round(volume, 2),
                "超重": gross_weight > weight_limit_kg(),
            }
        )
    if not by_box:
        return pd.DataFrame(columns=["箱号", "SKU种类", "件数", "净重(kg)", "毛重(kg)", "体积(cm3)", "超重"])
    return pd.DataFrame(by_box).sort_values("箱号")

