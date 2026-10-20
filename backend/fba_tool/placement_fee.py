"""亚马逊 FBA 入库配置服务费引擎 — 2026-01-15 生效政策。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from fba_tool.master_data_apply import build_placement_unit_rows

# S1e：判定用精确系数（1 in = 2.54 cm，1 lb = 0.45359237 kg）
CM_TO_IN = 1 / 2.54
KG_TO_LB = 1 / 0.45359237
DIM_WEIGHT_DIVISOR = 139.0

FeeRange = Tuple[float, float]
WeightTier = Tuple[float, float, Dict[str, FeeRange]]


def _tiers_from_policy() -> Dict[str, List[WeightTier]]:
    from fba_tool.policy import placement_classes

    tables: Dict[str, List[WeightTier]] = {}
    for name, rows in placement_classes().items():
        tiers: List[WeightTier] = []
        for row in rows:
            high = row.get("high")
            fees: Dict[str, FeeRange] = {}
            for key in ("1_loc", "2_3_loc", "5_loc"):
                if key in row and row[key] is not None:
                    pair = row[key]
                    fees[key] = (float(pair[0]), float(pair[1]))
            tiers.append((float(row.get("low") or 0), float("inf") if high is None else float(high), fees))
        tables[name] = tiers
    return tables


_RATE_TABLES = _tiers_from_policy()
LARGE_STANDARD_TIERS = _RATE_TABLES["large_standard"]
SMALL_OVERSIZE_TIERS = _RATE_TABLES["small_oversize"]

SIZE_CLASS_LABELS: Dict[str, str] = {
    "small_standard": "小号标准",
    "large_standard": "大号标准",
    "small_oversize": "小号大件",
    "large_oversize": "大号大件",
    "extra_large": "Extra-large",
}

STANDARD_SIZE_CLASSES = frozenset({"small_standard", "large_standard"})
FEE_SUPPORTED_CLASSES = frozenset(_RATE_TABLES)
OVERSIZE_CLASSES = frozenset({"small_oversize", "large_oversize", "extra_large"})

SPLIT_DISABLED_REASON_STANDARD = "标准尺寸商品不支持部分拆分入库"

SCENARIO_LABELS: Dict[str, str] = {
    "one_location": "单点入仓 (1仓)",
    "split_2_3": "部分拆分 (2-3仓)",
    "optimized_5": "亚马逊优化 (5仓+ · 免费)",
    "one_location_forced": "多分仓 · 标准尺寸按单点费率",
}

# 常见 FBA 目的仓 → 美西/美中/美东（财务汇报用）
WAREHOUSE_REGIONS: Dict[str, str] = {
    "ONT8": "美西",
    "LGB8": "美西",
    "SBD1": "美西",
    "SMF3": "美西",
    "PHX6": "美西",
    "GYR2": "美西",
    "MDW2": "美中",
    "IND9": "美中",
    "FWA4": "美东",
    "ORF2": "美东",
    "RDU2": "美东",
    "AVP1": "美东",
}


@dataclass(frozen=True)
class ChargeableWeight:
    actual_lb: float
    dimensional_lb: Optional[float]
    billing_lb: float
    volume_weight_applied: bool


class PlacementFeeEngine:
    """2026 入库配置服务费计算引擎。"""

    def __init__(self) -> None:
        self._rate_tables = _RATE_TABLES

    @staticmethod
    def kg_to_lb(weight_kg: float) -> float:
        return float(weight_kg) * KG_TO_LB

    @staticmethod
    def cm_to_in(value_cm: float) -> float:
        return float(value_cm) * CM_TO_IN

    @staticmethod
    def sorted_dims_in(l_cm: float, w_cm: float, h_cm: float) -> Tuple[float, float, float]:
        dims = sorted(
            [PlacementFeeEngine.cm_to_in(l_cm), PlacementFeeEngine.cm_to_in(w_cm), PlacementFeeEngine.cm_to_in(h_cm)],
            reverse=True,
        )
        return dims[0], dims[1], dims[2]

    @staticmethod
    def dimensional_weight_lb(longest_in: float, median_in: float, shortest_in: float) -> float:
        if longest_in <= 0 or median_in <= 0 or shortest_in <= 0:
            return 0.0
        return (longest_in * median_in * shortest_in) / DIM_WEIGHT_DIVISOR

    def resolve_chargeable_weight(
        self,
        weight_kg: float,
        l_cm: float,
        w_cm: float,
        h_cm: float,
        size_class: Optional[str],
    ) -> ChargeableWeight:
        actual_lb = self.kg_to_lb(weight_kg)
        has_dims = l_cm > 0 and w_cm > 0 and h_cm > 0

        if not has_dims:
            return ChargeableWeight(
                actual_lb=actual_lb,
                dimensional_lb=None,
                billing_lb=actual_lb,
                volume_weight_applied=False,
            )

        longest, median, shortest = self.sorted_dims_in(l_cm, w_cm, h_cm)
        dim_lb = self.dimensional_weight_lb(longest, median, shortest)

        if size_class == "small_standard":
            billing_lb = actual_lb
            volume_applied = False
        elif size_class in {"large_standard", "small_oversize", "large_oversize"}:
            billing_lb = max(actual_lb, dim_lb)
            volume_applied = dim_lb > actual_lb
        else:
            billing_lb = actual_lb
            volume_applied = False

        return ChargeableWeight(
            actual_lb=actual_lb,
            dimensional_lb=round(dim_lb, 3) if has_dims else None,
            billing_lb=billing_lb,
            volume_weight_applied=volume_applied,
        )

    def classify_size_tier(
        self,
        l_cm: float,
        w_cm: float,
        h_cm: float,
        weight_kg: float,
    ) -> Optional[str]:
        if l_cm <= 0 or w_cm <= 0 or h_cm <= 0:
            # 缺尺寸：按实重给出粗估分段（仅用于费用参考），compute_unit 会标注 low_confidence，
            # 提示运营补全外箱尺寸后才能得到精确费用。
            actual_lb = self.kg_to_lb(weight_kg)
            if actual_lb <= 0:
                return None
            if actual_lb <= 1.0:
                return "small_standard"
            if actual_lb <= 20.0:
                return "large_standard"
            if actual_lb <= 50.0:
                return "small_oversize"
            return "extra_large"

        from fba_tool.policy import size_limits

        limits = size_limits()
        longest, median, shortest = self.sorted_dims_in(l_cm, w_cm, h_cm)
        actual_lb = self.kg_to_lb(weight_kg)
        dim_lb = self.dimensional_weight_lb(longest, median, shortest)

        small = limits["small_standard"]
        if (
            longest <= small["longest"]
            and median <= small["median"]
            and shortest <= small["shortest"]
            and actual_lb <= small["weight_lb"]
        ):
            return "small_standard"

        billing_lb = max(actual_lb, dim_lb)
        large = limits["large_standard"]
        bulky = limits["small_oversize"]
        large_bulky = limits["large_oversize"]
        if (
            longest <= large["longest"]
            and median <= large["median"]
            and shortest <= large["shortest"]
            and billing_lb <= large["weight_lb"]
        ):
            return "large_standard"
        if (
            longest <= bulky["longest"]
            and median <= bulky["median"]
            and shortest <= bulky["shortest"]
            and billing_lb <= bulky["weight_lb"]
        ):
            return "small_oversize"
        if (
            longest <= large_bulky["longest"]
            and median <= large_bulky["median"]
            and shortest <= large_bulky["shortest"]
            and billing_lb <= large_bulky["weight_lb"]
        ):
            return "large_oversize"
        return "extra_large"

    @staticmethod
    def _match_weight_tier(billing_lb: float, tiers: List[WeightTier]) -> Optional[Dict[str, FeeRange]]:
        if billing_lb <= 0:
            return None
        prev_high = 0.0
        for low, high, fees in tiers:
            if low == 0.0:
                if billing_lb <= high + 1e-9:
                    return fees
            elif billing_lb > prev_high - 1e-9 and billing_lb <= high + 1e-9:
                return fees
            prev_high = high
        return None

    def lookup_fees(self, size_class: str, billing_lb: float) -> Optional[Dict[str, FeeRange]]:
        tiers = self._rate_tables.get(size_class)
        if not tiers:
            return None
        return self._match_weight_tier(billing_lb, tiers)

    @staticmethod
    def _fee_dict(min_usd: float, max_usd: float) -> Dict[str, float]:
        return {"min_usd": round(min_usd, 2), "max_usd": round(max_usd, 2)}

    @staticmethod
    def _scale_fee(fee: Optional[FeeRange], qty: int) -> Optional[Dict[str, float]]:
        if not fee or qty <= 0:
            return None
        return PlacementFeeEngine._fee_dict(fee[0] * qty, fee[1] * qty)

    def compute_unit(self, l_cm: float, w_cm: float, h_cm: float, weight_kg: float) -> Dict[str, Any]:
        size_class = self.classify_size_tier(l_cm, w_cm, h_cm, weight_kg)
        cw = self.resolve_chargeable_weight(weight_kg, l_cm, w_cm, h_cm, size_class)

        has_dims = l_cm > 0 and w_cm > 0 and h_cm > 0

        if not size_class or size_class not in FEE_SUPPORTED_CLASSES:
            reason = None
            low_confidence = False
            if not has_dims:
                reason = "单品包装尺寸缺失"
                low_confidence = True
            elif not size_class:
                reason = "无法判定尺寸分段或超出 50 lb 上限"
            return {
                "eligible": False,
                "size_class": size_class,
                "size_class_label": SIZE_CLASS_LABELS.get(size_class or "", "未知"),
                "actual_lb": round(cw.actual_lb, 3),
                "dimensional_lb": cw.dimensional_lb,
                "billing_lb": round(cw.billing_lb, 3),
                "volume_weight_applied": cw.volume_weight_applied,
                "split_2_3_disabled": True,
                "split_2_3_disabled_reason": SPLIT_DISABLED_REASON_STANDARD,
                "one_location": None,
                "split_2_3": None,
                "optimized_5": self._fee_dict(0.0, 0.0),
                "ineligible_reason": reason,
                "missing_dimensions": not has_dims,
                "low_confidence": low_confidence,
            }

        fees = self.lookup_fees(size_class, cw.billing_lb)
        if not fees:
            return {
                "eligible": False,
                "size_class": size_class,
                "size_class_label": SIZE_CLASS_LABELS[size_class],
                "actual_lb": round(cw.actual_lb, 3),
                "dimensional_lb": cw.dimensional_lb,
                "billing_lb": round(cw.billing_lb, 3),
                "volume_weight_applied": cw.volume_weight_applied,
                "split_2_3_disabled": size_class in STANDARD_SIZE_CLASSES,
                "split_2_3_disabled_reason": (
                    SPLIT_DISABLED_REASON_STANDARD if size_class in STANDARD_SIZE_CLASSES else None
                ),
                "one_location": None,
                "split_2_3": None,
                "optimized_5": self._fee_dict(0.0, 0.0),
                "ineligible_reason": "计费重量超出该尺寸分段费率表上限",
            }

        from fba_tool.policy import fee_disclaimer

        one_loc = fees.get("1_loc")
        split_23 = fees.get("2_3_loc")
        opt_5 = fees.get("5_loc", (0.0, 0.0))
        is_standard = size_class in STANDARD_SIZE_CLASSES

        return {
            "eligible": True,
            "size_class": size_class,
            "size_class_label": SIZE_CLASS_LABELS[size_class],
            "actual_lb": round(cw.actual_lb, 3),
            "dimensional_lb": cw.dimensional_lb,
            "billing_lb": round(cw.billing_lb, 3),
            "volume_weight_applied": cw.volume_weight_applied,
            "split_2_3_disabled": is_standard,
            "split_2_3_disabled_reason": SPLIT_DISABLED_REASON_STANDARD if is_standard else None,
            "one_location": self._fee_dict(*one_loc) if one_loc else None,
            "split_2_3": None if is_standard else (self._fee_dict(*split_23) if split_23 else None),
            "optimized_5": self._fee_dict(*opt_5),
            "ineligible_reason": None,
            "fee_disclaimer": fee_disclaimer(),
            "fee_note": "Extra-large：配置费 $0" if size_class == "extra_large" else None,
        }

    def compute_shipment(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        total_units = eligible_units = oversize_units = ineligible_units = 0
        missing_dimension_units = 0
        missing_dimension_skus: List[str] = []
        one_min = one_max = 0.0
        split_min = split_max = 0.0
        has_oversize_for_split = False
        has_standard_only = True
        line_items: List[Dict[str, Any]] = []

        for row in rows:
            sku = str(row.get("SKU简称") or "").strip()
            if not sku:
                continue
            qty = _to_int(row.get("发货总数"))
            if qty <= 0:
                continue

            l_cm = _to_float(row.get("unit_length_cm"))
            w_cm = _to_float(row.get("unit_width_cm"))
            h_cm = _to_float(row.get("unit_height_cm"))
            weight_kg = _to_float(row.get("unit_weight_kg"))

            total_units += qty
            unit = self.compute_unit(l_cm, w_cm, h_cm, weight_kg)

            line = {
                "sku": sku,
                "quantity": qty,
                **unit,
                "subtotal_one_location": self._scale_fee(
                    (unit["one_location"]["min_usd"], unit["one_location"]["max_usd"])
                    if unit.get("one_location")
                    else None,
                    qty,
                ),
                "subtotal_split_2_3": self._scale_fee(
                    (unit["split_2_3"]["min_usd"], unit["split_2_3"]["max_usd"])
                    if unit.get("split_2_3")
                    else None,
                    qty,
                ),
            }
            line_items.append(line)

            if not unit["eligible"]:
                ineligible_units += qty
                continue

            eligible_units += qty
            if unit["one_location"]:
                one_min += unit["one_location"]["min_usd"] * qty
                one_max += unit["one_location"]["max_usd"] * qty

            if unit["size_class"] in OVERSIZE_CLASSES:
                has_standard_only = False
            if unit["size_class"] in OVERSIZE_CLASSES and unit.get("split_2_3"):
                has_oversize_for_split = True
                oversize_units += qty
                split_min += unit["split_2_3"]["min_usd"] * qty
                split_max += unit["split_2_3"]["max_usd"] * qty

        split_enabled = has_oversize_for_split
        split_disabled_reason: Optional[str] = None
        if not split_enabled:
            split_disabled_reason = (
                SPLIT_DISABLED_REASON_STANDARD
                if has_standard_only and eligible_units > 0
                else "当前货件无可用大件 SKU，无法使用 2-3 仓拆分"
            )

        from fba_tool.policy import fee_disclaimer

        return {
            "total_units": total_units,
            "eligible_units": eligible_units,
            "oversize_units": oversize_units,
            "ineligible_units": ineligible_units,
            "fee_disclaimer": fee_disclaimer(),
            "line_items": line_items,
            "one_location": {
                "enabled": eligible_units > 0,
                "min_usd": round(one_min, 2),
                "max_usd": round(one_max, 2),
            },
            "split_2_3": {
                "enabled": split_enabled,
                "disabled_reason": split_disabled_reason,
                "min_usd": round(split_min, 2) if split_enabled else None,
                "max_usd": round(split_max, 2) if split_enabled else None,
            },
            "optimized_5": {
                "enabled": True,
                "min_usd": 0.0,
                "max_usd": 0.0,
            },
        }


_engine = PlacementFeeEngine()


def compute_shipment_placement_fees(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _engine.compute_shipment(rows)


def compute_unit_placement_fees(
    l_cm: float,
    w_cm: float,
    h_cm: float,
    weight_kg: float,
) -> Dict[str, Any]:
    return _engine.compute_unit(l_cm, w_cm, h_cm, weight_kg)


def classify_placement_scenario(location_count: int) -> str:
    """根据实际目的仓数量判定入库配置费方案。"""
    if location_count <= 0:
        return "one_location"
    if location_count == 1:
        return "one_location"
    if location_count <= 4:
        return "split_2_3"
    return "optimized_5"


def _scenario_line_totals(line_items: List[Dict[str, Any]], scenario: str) -> Tuple[float, float]:
    total_min = total_max = 0.0
    for line in line_items:
        if not line.get("eligible"):
            continue
        if scenario == "one_location":
            sub = line.get("subtotal_one_location")
            if sub:
                total_min += float(sub["min_usd"])
                total_max += float(sub["max_usd"])
        elif scenario == "split_2_3":
            if line.get("split_2_3") and line.get("subtotal_split_2_3"):
                sub = line["subtotal_split_2_3"]
                total_min += float(sub["min_usd"])
                total_max += float(sub["max_usd"])
            elif line.get("subtotal_one_location"):
                sub = line["subtotal_one_location"]
                total_min += float(sub["min_usd"])
                total_max += float(sub["max_usd"])
    return round(total_min, 2), round(total_max, 2)


def warehouse_region(code: str) -> str:
    return WAREHOUSE_REGIONS.get(str(code or "").strip().upper(), "其他")


def compute_locked_placement_fee(
    rows: List[Dict[str, Any]],
    warehouse_codes: List[str],
) -> Dict[str, Any]:
    """
    Step 4 校验通过后：根据实际目的仓数量，将 Step 1 区间预估锁定为定数。

    锁定规则：locked_usd 取适用方案 composite 区间的 max_usd（财务保守预算）。
    同时给出 applicable_range_mid_usd 作为定价/毛利测算用的预期值——
    只看上限会系统性高估成本，导致误判 SKU 不赚钱。
    """
    unit_rows = build_placement_unit_rows(rows) if rows else []
    estimate = _engine.compute_shipment(unit_rows)

    warehouses = sorted({str(w).strip().upper() for w in warehouse_codes if str(w).strip()})
    loc_count = len(warehouses)
    scenario = classify_placement_scenario(loc_count)

    if scenario == "optimized_5":
        applicable_min = applicable_max = locked = 0.0
        scenario_label = SCENARIO_LABELS["optimized_5"]
    elif scenario == "split_2_3" and estimate["split_2_3"]["enabled"]:
        applicable_min, applicable_max = _scenario_line_totals(estimate["line_items"], "split_2_3")
        locked = applicable_max
        scenario_label = SCENARIO_LABELS["split_2_3"]
    elif scenario == "split_2_3" and not estimate["split_2_3"]["enabled"]:
        scenario = "one_location_forced"
        applicable_min, applicable_max = _scenario_line_totals(estimate["line_items"], "one_location")
        locked = applicable_max
        scenario_label = SCENARIO_LABELS["one_location_forced"]
    else:
        applicable_min, applicable_max = _scenario_line_totals(estimate["line_items"], "one_location")
        locked = applicable_max
        scenario_label = SCENARIO_LABELS["one_location"]

    regions = sorted({warehouse_region(w) for w in warehouses})

    return {
        "status": "locked",
        "actual_location_count": loc_count,
        "actual_warehouses": warehouses,
        "warehouse_regions": regions,
        "scenario": scenario,
        "scenario_label": scenario_label,
        "step1_preview": {
            "one_location": estimate["one_location"],
            "split_2_3": estimate["split_2_3"],
            "optimized_5": estimate["optimized_5"],
        },
        "applicable_range_min_usd": applicable_min,
        "applicable_range_max_usd": applicable_max,
        "applicable_range_mid_usd": round((applicable_min + applicable_max) / 2, 2),
        "locked_usd": round(locked, 2),
        "lock_method": "range_max",
        "eligible_units": estimate["eligible_units"],
        "total_units": estimate["total_units"],
    }


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
