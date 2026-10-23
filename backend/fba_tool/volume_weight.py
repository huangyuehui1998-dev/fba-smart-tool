from __future__ import annotations

import re
from typing import Literal

from fba_tool.units import INCH_TO_CM, LB_TO_KG
from fba_tool.user_config import param, throw_ratio as config_throw_ratio

DimUnit = Literal["in", "cm"]
WeightUnit = Literal["lb", "kg"]


def detect_length_unit(label: str) -> DimUnit:
    text = str(label or "").lower()
    if any(k in text for k in ("英寸", "inch", "in)", "in）", "(in")):
        return "in"
    return "cm"


def detect_weight_unit(label: str) -> WeightUnit:
    text = str(label or "").lower()
    if any(k in text for k in ("磅", "lb", "pound")):
        return "lb"
    return "kg"


def to_cm(value: float, unit: DimUnit | str) -> float:
    """底层统一为 cm。已经是厘米的保留原精度（44.96 不再收成 45.00）。

    英寸按配置系数换算后保留 2 位：17.70 in × 2.54 = 44.96。
    """
    if value <= 0:
        return 0.0
    if str(unit).lower() in {"in", "inch", "inches", "英寸"}:
        value = float(value) * float(param("inch_to_cm_factor", INCH_TO_CM))
        return round(float(value), 2)
    return float(value)


def to_kg(value: float, unit: WeightUnit | str) -> float:
    """底层统一为 kg；磅按配置系数换算后保留 2 位小数。"""
    if value <= 0:
        return 0.0
    if str(unit).lower() in {"lb", "lbs", "pound", "pounds", "磅"}:
        value = float(value) * float(param("lb_to_kg_factor", LB_TO_KG))
    return round(float(value), 2)


def box_cbm(length_cm: float, width_cm: float, height_cm: float) -> float:
    """单箱方数 (CBM) = 长(cm) × 宽(cm) × 高(cm) ÷ 1,000,000"""
    l, w, h = to_cm(length_cm, "cm"), to_cm(width_cm, "cm"), to_cm(height_cm, "cm")
    if l <= 0 or w <= 0 or h <= 0:
        return 0.0
    return round(l * w * h / 1_000_000, 3)


def volume_weight_kg(
    length_cm: float,
    width_cm: float,
    height_cm: float,
    throw_ratio: float | None = None,
) -> float:
    """单箱体积重 (kg) = 长(cm) × 宽(cm) × 高(cm) ÷ 抛重系数"""
    ratio = float(throw_ratio if throw_ratio is not None else config_throw_ratio())
    if ratio <= 0:
        return 0.0
    l, w, h = to_cm(length_cm, "cm"), to_cm(width_cm, "cm"), to_cm(height_cm, "cm")
    if l <= 0 or w <= 0 or h <= 0:
        return 0.0
    return round(l * w * h / ratio, 3)


def normalize_box_spec_row(
    length_raw: float,
    width_raw: float,
    height_raw: float,
    weight_raw: float,
    length_unit: DimUnit | str = "in",
    width_unit: DimUnit | str | None = None,
    height_unit: DimUnit | str | None = None,
    weight_unit: WeightUnit | str = "lb",
) -> dict[str, float]:
    """步骤 2：单位换算 + 精度容差抹平。"""
    wu = width_unit or length_unit
    hu = height_unit or length_unit
    return {
        "长(cm)": to_cm(length_raw, length_unit),
        "宽(cm)": to_cm(width_raw, wu),
        "高(cm)": to_cm(height_raw, hu),
        "实重(kg)": to_kg(weight_raw, weight_unit),
    }


def is_packaging_label(label: str) -> bool:
    text = str(label or "").strip().lower()
    if not text:
        return False
    if any(k in text for k in ("包装箱", "箱号", "编号", "箱子名称")):
        return True
    return bool(re.search(r"(packaging|box).*(length|width|height|weight)", text, flags=re.I))
