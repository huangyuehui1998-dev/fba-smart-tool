"""单箱毛重的唯一入口。

整箱且录了单箱毛重时用录入值；否则用 数量 × 单重 + 空箱重。
混装箱的空箱重取箱内体积最大的那个 SKU 的外箱皮重，不取各 SKU 皮重的最大值。
"""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Optional


def _finite(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def carton_gross_kg(
    qty: Any,
    unit_kg: Any,
    tare_kg: Any,
    declared_gross_kg: Any = None,
    full_carton_qty: Any = None,
) -> float:
    """整箱且录入值 > 0 时取录入值，否则取数量×单重+空箱重。"""
    pieces = _finite(qty) or 0.0
    unit = _finite(unit_kg) or 0.0
    tare = _finite(tare_kg) or 0.0
    declared = _finite(declared_gross_kg)
    full = _finite(full_carton_qty)
    is_full = full is not None and pieces > 0 and pieces == full
    if is_full and declared is not None and declared > 0:
        return round(declared, 3)
    return round(pieces * unit + tare, 3)


def _sku_name(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item.get("sku") or item.get("SKU简称") or "").strip()
    return str(getattr(item, "sku", "") or "").strip()


def _volume(sku: Any) -> float:
    return float(getattr(sku, "length_cm", 0) or 0) * float(getattr(sku, "width_cm", 0) or 0) * float(
        getattr(sku, "height_cm", 0) or 0
    )


def carrier_sku(items: Iterable[Any], sku_map: Dict[str, Any]) -> Any:
    """混装箱的承载外箱：箱内体积最大的 SKU。体积相同取先出现的。"""
    best = None
    best_vol = -1.0
    for item in items:
        name = _sku_name(item)
        sku = sku_map.get(name)
        if sku is None:
            continue
        vol = _volume(sku)
        if vol > best_vol:
            best, best_vol = sku, vol
    return best


def carrier_tare(items: Iterable[Any], sku_map: Dict[str, Any]) -> float:
    sku = carrier_sku(items, sku_map)
    if sku is None:
        return 0.0
    return float(getattr(sku, "carton_tare_kg", 0) or 0)


def mixed_box_would_exceed(net_kg: Any, add_kg: Any, tare_kg: Any, max_kg: Any) -> bool:
    """净重 + 将放入的重量 + 承载箱皮重 是否超过上限。等于上限不算超。"""
    net = _finite(net_kg) or 0.0
    add = _finite(add_kg) or 0.0
    tare = _finite(tare_kg) or 0.0
    limit = _finite(max_kg)
    if limit is None:
        return False
    return (net + add + tare) > limit


def box_gross_kg(lines: Iterable[Any], sku_map: Dict[str, Any]) -> float:
    """lines 是 (sku 名, 数量)。单 SKU 整箱走录入值，混装走净重+承载箱皮重。"""
    parsed = []
    net = 0.0
    for line in lines:
        if isinstance(line, dict):
            name = _sku_name(line)
            qty = int(_finite(line.get("qty") or line.get("数量")) or 0)
        else:
            name, qty = line
            name = str(name).strip()
            qty = int(_finite(qty) or 0)
        sku = sku_map.get(name)
        if sku is None or qty <= 0:
            continue
        net += float(getattr(sku, "unit_weight_kg", 0) or 0) * qty
        parsed.append((sku, qty))
    if not parsed:
        return 0.0
    if len(parsed) == 1:
        sku, qty = parsed[0]
        return carton_gross_kg(
            qty,
            sku.unit_weight_kg,
            sku.carton_tare_kg,
            sku.carton_gross_kg,
            sku.carton_qty,
        )
    return round(net + carrier_tare([sku.sku for sku, _qty in parsed], sku_map), 3)
