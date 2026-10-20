from __future__ import annotations

from fba_tool.user_config import param


def cm_to_inch(v: float) -> float:
    return round(v * float(param("cm_to_inch_factor", 0.393701)), 3)


def kg_to_lb(v: float) -> float:
    return round(v * float(param("kg_to_lb_factor", 2.20462)), 3)


def inch_to_cm(v: float) -> float:
    return round(v * float(param("inch_to_cm_factor", 2.54)), 2)


def lb_to_kg(v: float) -> float:
    return round(v * float(param("lb_to_kg_factor", 0.453592)), 3)
