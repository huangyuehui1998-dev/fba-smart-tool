"""海运/空运核心物流指标：密度、积载因数、W/M、计费吨。"""
from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from fba_tool.user_config import throw_ratio as default_throw_ratio
from fba_tool.volume_weight import box_cbm, volume_weight_kg


def compute_logistics_metrics(
    *,
    total_net_kg: float,
    total_gross_kg: float,
    total_cbm: float,
    total_volumetric_weight_kg: float,
    density_is_approx: bool = False,
) -> Dict[str, Any]:
    """计算四项核心指标并返回统一 JSON 字段。

    density_is_approx=True 表示净重数据缺失、密度以毛重近似（会偏高），
    供前端提示用户该密度仅供参考。
    """
    net = max(0.0, float(total_net_kg or 0))
    gross = max(0.0, float(total_gross_kg or 0))
    cbm = max(0.0, float(total_cbm or 0))
    vol = max(0.0, float(total_volumetric_weight_kg or 0))

    cargo_density = round(net / cbm, 3) if cbm > 0 else 0.0
    stowage_factor = round(cbm / (gross / 1000), 3) if gross > 0 else 0.0
    wm_ratio = "重货 (Weight)" if gross >= vol else "泡货 (Measurement)"
    revenue_ton = round(max(gross, vol), 3)

    return {
        "total_net_kg": round(net, 3),
        "total_gross_kg": round(gross, 3),
        "total_cbm": round(cbm, 3),
        "total_volumetric_weight_kg": round(vol, 3),
        "cargo_density": cargo_density,
        "cargo_density_is_approx": bool(density_is_approx),
        "stowage_factor": stowage_factor,
        "wm_ratio": wm_ratio,
        "revenue_ton": revenue_ton,
    }


def logistics_metrics_from_box_specs(
    box_specs_df: pd.DataFrame,
    throw_ratio_val: float | None = None,
) -> Dict[str, Any]:
    """Step 4 实测箱规：汇总毛重、方数、体积重并计算指标。"""
    ratio = float(throw_ratio_val if throw_ratio_val is not None else default_throw_ratio())
    if box_specs_df.empty:
        return compute_logistics_metrics(
            total_net_kg=0,
            total_gross_kg=0,
            total_cbm=0,
            total_volumetric_weight_kg=0,
        )

    total_gross = 0.0
    total_cbm = 0.0
    total_vol = 0.0

    for _, row in box_specs_df.iterrows():
        l = float(row.get("长(cm)", 0) or 0)
        w = float(row.get("宽(cm)", 0) or 0)
        h = float(row.get("高(cm)", 0) or 0)
        gross = float(row.get("实重(kg)", 0) or 0)
        if l <= 0 or w <= 0 or h <= 0 or gross <= 0:
            continue
        total_gross += gross
        total_cbm += box_cbm(l, w, h)
        total_vol += volume_weight_kg(l, w, h, throw_ratio=ratio)

    # Step 4 CSV 箱规仅有单箱实重，净重以实重汇总近似
    return compute_logistics_metrics(
        total_net_kg=total_gross,
        total_gross_kg=total_gross,
        total_cbm=round(total_cbm, 3),
        total_volumetric_weight_kg=round(total_vol, 3),
        density_is_approx=True,
    )
