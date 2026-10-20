from __future__ import annotations

from fba_tool.units import CM_TO_INCH, INCH_TO_CM, KG_TO_LB, LB_TO_KG
from fba_tool.user_config import param


def cm_to_inch(v: float) -> float:
    return round(v * float(param("cm_to_inch_factor", CM_TO_INCH)), 3)


def kg_to_lb(v: float) -> float:
    return round(v * float(param("kg_to_lb_factor", KG_TO_LB)), 3)


def inch_to_cm(v: float) -> float:
    return round(v * float(param("inch_to_cm_factor", INCH_TO_CM)), 2)


def lb_to_kg(v: float) -> float:
    return round(v * float(param("lb_to_kg_factor", LB_TO_KG)), 3)
