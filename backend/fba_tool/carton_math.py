"""箱规对比的纯计算。换算系数与 TD-2 相同：1 in = 2.54 cm，1 lb = 0.45359237 kg。"""
from __future__ import annotations

import re
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from fba_tool.units import CM_PER_IN, LB_IN_KG

FBA_BOX_RE = re.compile(r"^FBA[0-9A-Z]+U[0-9]+$", re.IGNORECASE)
_CENT = Decimal("0.01")
_MM = Decimal("0.001")
_TENTH = Decimal("0.1")
_CM_SLACK = Decimal("0.05")

DEFAULT_DIM_DIVISOR = Decimal("6000")
DEFAULT_TOLERANCES = {
    "side_normal_cm": Decimal("1.0"),
    "side_warn_cm": Decimal("2.5"),
    "side_pct": Decimal("5"),
    "weight_normal_kg": Decimal("0.3"),
    "weight_normal_pct": Decimal("5"),
    "weight_warn_pct": Decimal("10"),
    "chargeable_normal_pct": Decimal("3"),
    "chargeable_warn_pct": Decimal("10"),
    "volume_bias_pct": Decimal("5"),
    "volume_bias_share": Decimal("0.80"),
    "bill_warn_kg": Decimal("1"),
}


def D(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(str(value).strip())


def q(value: Any, places: int) -> Decimal:
    quantum = Decimal("1").scaleb(-places)
    return D(value).quantize(quantum, rounding=ROUND_HALF_UP)


def inches_to_cm(inches: Any) -> Decimal:
    return q(D(inches) * CM_PER_IN, 2)


def cm_to_inches(cm: Any) -> Decimal:
    return q(D(cm) / CM_PER_IN, 2)


def lb_to_kg(lb: Any) -> Decimal:
    return q(D(lb) * LB_IN_KG, 3)


def roundtrip_cm_delta(cm: Any) -> Decimal:
    """厘米 → 英寸（2 位）→ 厘米。往返差不超过 0.05cm 记为 0。"""
    back = inches_to_cm(cm_to_inches(cm))
    delta = back - q(cm, 2)
    if abs(delta) <= _CM_SLACK:
        return Decimal("0")
    return delta


def _zero_slack(delta: Decimal) -> Decimal:
    if abs(delta) <= _CM_SLACK:
        return Decimal("0")
    return delta


def sorted_dims(dims: Sequence[Any]) -> Tuple[Decimal, Decimal, Decimal]:
    ordered = sorted((q(d, 2) for d in dims), reverse=True)
    if len(ordered) != 3:
        raise ValueError("尺寸必须是长宽高三项")
    return ordered[0], ordered[1], ordered[2]


def dim_deltas(declared: Sequence[Any], measured: Sequence[Any]) -> Tuple[Decimal, Decimal, Decimal]:
    left = sorted_dims(declared)
    right = sorted_dims(measured)
    return tuple(_zero_slack(right[i] - left[i]) for i in range(3))  # type: ignore[return-value]


def original_order_deltas(declared: Sequence[Any], measured: Sequence[Any]) -> Tuple[Decimal, Decimal, Decimal]:
    return tuple(_zero_slack(q(measured[i], 2) - q(declared[i], 2)) for i in range(3))  # type: ignore[return-value]


def volumetric_kg(length: Any, width: Any, height: Any, divisor: Any = DEFAULT_DIM_DIVISOR) -> Decimal:
    div = D(divisor)
    if div <= 0:
        raise ValueError("体积重除数必须大于 0")
    return q(D(length) * D(width) * D(height) / div, 2)


def chargeable_kg(weight: Any, dims: Sequence[Any], divisor: Any = DEFAULT_DIM_DIVISOR) -> Decimal:
    return max(q(weight, 3), volumetric_kg(dims[0], dims[1], dims[2], divisor))


def _pct(delta: Decimal, base: Decimal) -> Decimal:
    if base == 0:
        return Decimal("0")
    return abs(delta) / abs(base) * Decimal("100")


def side_level(delta_cm: Any, base_cm: Any, tolerances: Optional[Dict[str, Decimal]] = None) -> str:
    tol = {**DEFAULT_TOLERANCES, **(tolerances or {})}
    delta = abs(D(delta_cm))
    pct = _pct(D(delta_cm), D(base_cm))
    if delta > tol["side_warn_cm"] or pct > tol["side_pct"]:
        return "异常"
    if delta > tol["side_normal_cm"]:
        return "提示"
    return "正常"


def weight_level(delta_kg: Any, base_kg: Any, tolerances: Optional[Dict[str, Decimal]] = None) -> str:
    tol = {**DEFAULT_TOLERANCES, **(tolerances or {})}
    delta = abs(D(delta_kg))
    pct = _pct(D(delta_kg), D(base_kg))
    if pct > tol["weight_warn_pct"]:
        return "异常"
    if pct > tol["weight_normal_pct"] or delta > tol["weight_normal_kg"]:
        return "提示"
    return "正常"


def chargeable_level(delta_kg: Any, base_kg: Any, tolerances: Optional[Dict[str, Decimal]] = None) -> str:
    tol = {**DEFAULT_TOLERANCES, **(tolerances or {})}
    pct = _pct(D(delta_kg), D(base_kg))
    if pct > tol["chargeable_warn_pct"]:
        return "异常"
    if pct > tol["chargeable_normal_pct"]:
        return "提示"
    return "正常"


def worst_level(*levels: str) -> str:
    rank = {"正常": 0, "提示": 1, "异常": 2}
    return max(levels, key=lambda item: rank.get(item, 0))


def box_status(
    declared_dims: Sequence[Any],
    measured_dims: Sequence[Any],
    declared_kg: Any,
    measured_kg: Any,
    divisor: Any = DEFAULT_DIM_DIVISOR,
    tolerances: Optional[Dict[str, Decimal]] = None,
) -> str:
    deltas = dim_deltas(declared_dims, measured_dims)
    declared_sorted = sorted_dims(declared_dims)
    sides = [side_level(deltas[i], declared_sorted[i], tolerances) for i in range(3)]
    weight = weight_level(D(measured_kg) - D(declared_kg), D(declared_kg), tolerances)
    decl_cw = chargeable_kg(declared_kg, declared_dims, divisor)
    meas_cw = chargeable_kg(measured_kg, measured_dims, divisor)
    charge = chargeable_level(meas_cw - decl_cw, decl_cw, tolerances)
    return worst_level(*sides, weight, charge)


def is_fba_box_id(value: Any) -> bool:
    return bool(FBA_BOX_RE.match(str(value or "").strip()))


def signed(value: Any, places: int = 2, plus: bool = True) -> str:
    number = q(value, places)
    text = f"{number:.{places}f}"
    if number > 0 and plus:
        return f"+{text}"
    if number < 0:
        return "−" + f"{abs(number):.{places}f}"
    return f"{Decimal('0'):.{places}f}"


def volume_of(dims: Sequence[Any]) -> Decimal:
    return D(dims[0]) * D(dims[1]) * D(dims[2])


def suggest_spec_update(rows: Sequence[Dict[str, Any]], tolerances: Optional[Dict[str, Decimal]] = None) -> bool:
    """实测体积均值比申报大过阈值，且超过 80% 的箱为正，才提示更新箱规。"""
    tol = {**DEFAULT_TOLERANCES, **(tolerances or {})}
    if not rows:
        return False
    ratios: List[Decimal] = []
    for row in rows:
        base = volume_of(row["declared_dims"])
        if base <= 0:
            continue
        ratios.append((volume_of(row["measured_dims"]) - base) / base)
    if not ratios:
        return False
    mean = sum(ratios) / Decimal(len(ratios))
    positive = sum(1 for item in ratios if item > 0)
    return mean > tol["volume_bias_pct"] / Decimal("100") and (Decimal(positive) / Decimal(len(ratios))) > tol["volume_bias_share"]


def format_volume_bias_pct(ratio: Any) -> str:
    """显示 1 位。14.95% 按方案显示为 +14.9%（向 0 截断到 1 位）。"""
    shown = (D(ratio) * Decimal("100")).quantize(_TENTH, rounding=ROUND_DOWN)
    return signed(shown, 1) + "%"


def decompose(
    matched_rows: Sequence[Dict[str, Any]],
    tickets: Sequence[Dict[str, Any]],
    divisor: Any = DEFAULT_DIM_DIVISOR,
) -> Dict[str, Decimal]:
    """计费重可加分解。matched_rows 只用去重后的精确匹配行；tickets 用每票全部过机行。"""
    weight = Decimal("0")
    size = Decimal("0")
    box = Decimal("0")
    actual = Decimal("0")
    for row in matched_rows:
        decl_dims = row["declared_dims"]
        meas_dims = row["measured_dims"]
        decl_cw = chargeable_kg(row["declared_kg"], decl_dims, divisor)
        meas_on_decl = chargeable_kg(row["measured_kg"], decl_dims, divisor)
        meas_cw = chargeable_kg(row["measured_kg"], meas_dims, divisor)
        weight += meas_on_decl - decl_cw
        size += meas_cw - meas_on_decl
        box += meas_cw - decl_cw
        actual += q(row["measured_kg"], 3) - q(row["declared_kg"], 3)
    carry = Decimal("0")
    for ticket in tickets:
        line_sum = Decimal("0")
        for scan in ticket.get("rows") or []:
            dims = scan.get("dims")
            if dims:
                line_sum += chargeable_kg(scan["weight_kg"], dims, divisor)
            else:
                line_sum += q(scan.get("chargeable_kg") if scan.get("chargeable_kg") is not None else scan["weight_kg"], 3)
        carry += q(ticket["bill_kg"], 2) - q(line_sum, 2)
    total = weight + size + carry
    return {
        "weight_contrib": q(weight, 2),
        "size_contrib": q(size, 2),
        "box_total": q(box, 2),
        "carry": q(carry, 2),
        "total": q(total, 2),
        "actual_delta": q(actual, 2),
    }


def summary_lines(parts: Dict[str, Decimal], deduped_count: int, duplicate_ids: Sequence[str]) -> Dict[str, str]:
    headline = (
        f"计费重总差 {signed(parts['total'])}kg = 实重贡献 {signed(parts['weight_contrib'])}"
        f" + 尺寸贡献 {signed(parts['size_contrib'])} + 进位 {signed(parts['carry'])}（全票口径）"
    )
    reference = f"实重差 {signed(parts['actual_delta'])}kg（仅参考，去重 {deduped_count} 箱）"
    count = len(duplicate_ids)
    note = f"{count} 个重复箱号未计入汇总"
    detail = ""
    if count:
        shown = "、".join(duplicate_ids)
        detail = f"{count} 个重复箱号未计入汇总（{shown}，2 条过机记录见质量区）" if count == 1 else (
            f"{count} 个重复箱号未计入汇总（{shown}，过机记录见质量区）"
        )
    return {"headline": headline, "reference": reference, "dup_note": note, "dup_detail": detail}


def flag_suspected_mixups(rows: Sequence[Dict[str, Any]], tolerances: Optional[Dict[str, Decimal]] = None) -> List[Dict[str, Any]]:
    """偏离本 SKU 中位数、且接近另一个 SKU 中位数的箱。文案只写疑似。"""
    grouped: Dict[str, List[Decimal]] = {}
    for row in rows:
        grouped.setdefault(str(row["sku"]), []).append(D(row["weight_kg"]))
    medians = {sku: D(median(values)) for sku, values in grouped.items() if values}
    flagged: List[Dict[str, Any]] = []
    for row in rows:
        sku = str(row["sku"])
        own = medians.get(sku)
        if own is None:
            continue
        weight = D(row["weight_kg"])
        if weight_level(weight - own, own, tolerances) == "正常":
            continue
        for other, center in medians.items():
            if other == sku:
                continue
            if weight_level(weight - center, center, tolerances) == "正常":
                flagged.append({
                    "id": row.get("id"),
                    "sku": sku,
                    "weight_kg": weight,
                    "other_sku": other,
                    "label": "疑似装错 SKU（推断，待货代/工厂核实）",
                })
                break
    return flagged


def light_heavy_check(
    declared_kg: Sequence[Any],
    measured_rows: Sequence[Dict[str, Any]],
    threshold: Any = None,
) -> Dict[str, Any]:
    bands = sorted({q(item, 3) for item in declared_kg})
    if len(bands) < 2:
        return {"enabled": False, "message": "", "threshold_kg": None}
    if threshold is None:
        threshold = (bands[0] + bands[-1]) / Decimal("2")
    limit = D(threshold)
    declared_light = sum(1 for item in declared_kg if D(item) < limit)
    declared_heavy = len(list(declared_kg)) - declared_light
    measured_values = [D(row["weight_kg"]) for row in measured_rows]
    measured_light = sum(1 for item in measured_values if item < limit)
    measured_heavy = len(measured_values) - measured_light
    message = ""
    if measured_light != declared_light or measured_heavy != declared_heavy:
        parts = []
        light_gap = measured_light - declared_light
        heavy_gap = measured_heavy - declared_heavy
        if light_gap:
            parts.append(f"轻箱{'多' if light_gap > 0 else '少'} {abs(light_gap)}")
        if heavy_gap:
            parts.append(f"重箱{'多' if heavy_gap > 0 else '少'} {abs(heavy_gap)}")
        message = "、".join(parts)
    return {
        "enabled": True,
        "threshold_kg": q(limit, 3),
        "declared_light": declared_light,
        "declared_heavy": declared_heavy,
        "measured_light": measured_light,
        "measured_heavy": measured_heavy,
        "message": message,
        "scope": "全部过机行",
    }


def bill_warnings(tickets: Sequence[Dict[str, Any]], divisor: Any = DEFAULT_DIM_DIVISOR) -> List[str]:
    notes: List[str] = []
    for ticket in tickets:
        line_sum = Decimal("0")
        for scan in ticket.get("rows") or []:
            dims = scan.get("dims")
            if dims:
                line_sum += chargeable_kg(scan["weight_kg"], dims, divisor)
            else:
                line_sum += q(scan.get("chargeable_kg") if scan.get("chargeable_kg") is not None else scan["weight_kg"], 3)
        gap = q(ticket["bill_kg"], 2) - q(line_sum, 2)
        if gap > DEFAULT_TOLERANCES["bill_warn_kg"]:
            notes.append("货代账单计费重偏高，请核对")
            break
    return notes


def classify_measurements(
    declared_ids: Iterable[str],
    measured_ids: Sequence[str],
) -> List[str]:
    """按完整箱号精确匹配。返回与 measured_ids 等长的 match_status。"""
    declared = {str(item).strip().upper() for item in declared_ids}
    counts: Dict[str, int] = {}
    normalized = [str(item or "").strip().upper() for item in measured_ids]
    for item in normalized:
        counts[item] = counts.get(item, 0) + 1
    statuses: List[str] = []
    for item in normalized:
        if not is_fba_box_id(item):
            statuses.append("invalid_id")
        elif counts[item] > 1:
            statuses.append("duplicate")
        elif item not in declared:
            statuses.append("unmatched")
        else:
            statuses.append("matched")
    return statuses


def missing_declared(declared_ids: Iterable[str], measured_ids: Sequence[str]) -> List[str]:
    seen = {str(item or "").strip().upper() for item in measured_ids}
    missing = []
    for item in declared_ids:
        key = str(item).strip().upper()
        if key and key not in seen:
            missing.append(key)
    return missing


def net_from_tares(gross: Any, tares: Sequence[Any]) -> Decimal:
    from fba_tool.customs_package import money_half_up, to_dec

    net = to_dec(gross)
    for tare in tares:
        net -= to_dec(tare)
    if net < 0:
        net = Decimal("0")
    return money_half_up(net)


def published_batch13_identity() -> Dict[str, Decimal]:
    """方案 9.9 公布的可加分解，不读取任何真实批次文件。"""
    weight = Decimal("0.00")
    size = Decimal("318.71")
    carry = Decimal("1.30")
    return {
        "weight_contrib": weight,
        "size_contrib": size,
        "carry": carry,
        "total": weight + size + carry,
        "actual_delta": Decimal("-28.37"),
        "reconcile_total": Decimal("0.00") + Decimal("322.55") + Decimal("1.30"),
    }
