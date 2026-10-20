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
    current_items: List[BoxItem] = []
    current_weight = 0.0
    current_volume = 0.0
    current_count = 0
    for tail in tail_pool:
        qty_left = int(tail["剩余数量"])
        unit_weight = float(tail["单个重量(kg)"] or 0)
        unit_vol = float(tail["单件体积(cm3)"] or 0)
        sku_name = str(tail["SKU简称"])
        while qty_left > 0:
            tare = carrier_tare([it.sku for it in current_items] + [sku_name], sku_map)
            over_weight = mixed_box_would_exceed(current_weight, unit_weight, tare, max_weight_kg)
            if (current_count >= max_mixed_items or
                over_weight or
                current_volume + unit_vol > usable_volume):

                if current_items:
                    plans.append(BoxPlan(box_no=box_no, items=current_items, source="混装"))
                    box_no += 1
                current_items = []
                current_weight = 0.0
                current_volume = 0.0
                current_count = 0
            current_items.append(BoxItem(sku=tail["SKU简称"], qty=1))
            current_weight += unit_weight
            current_volume += unit_vol
            current_count += 1
            qty_left -= 1
    if current_items:
        plans.append(BoxPlan(box_no=box_no, items=current_items, source="混装"))

    return plans, pd.DataFrame(tail_pool)


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

