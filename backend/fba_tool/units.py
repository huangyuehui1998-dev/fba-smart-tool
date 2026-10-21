"""长度和重量换算的唯一系数。

1 in = 2.54 cm，1 lb = 0.45359237 kg。千克转磅用倒数，不在源码里写另一套近似系数。
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

LB_IN_KG = Decimal("0.45359237")
CM_PER_IN = Decimal("2.54")
LB_TO_KG = float(LB_IN_KG)
INCH_TO_CM = float(CM_PER_IN)
KG_TO_LB = float(Decimal(1) / LB_IN_KG)
CM_TO_INCH = float(Decimal(1) / CM_PER_IN)


def kg_to_lb_exact(kg) -> Decimal:
    return Decimal(str(kg)) / LB_IN_KG


def kg_to_lb(kg, places: int = 2) -> float:
    quantum = Decimal("1").scaleb(-places)
    return float(kg_to_lb_exact(kg).quantize(quantum, rounding=ROUND_HALF_UP))


def lb_to_kg_exact(lb) -> Decimal:
    return Decimal(str(lb)) * LB_IN_KG
