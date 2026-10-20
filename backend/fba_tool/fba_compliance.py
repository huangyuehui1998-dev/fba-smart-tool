"""亚马逊 FBA 入库纸箱物理红线校验（拒收 / Inbound Defect Fee 风险）。"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from fba_tool.models import SkuRow
from fba_tool.placement_fee import PlacementFeeEngine
from fba_tool.user_config import amazon_max_boxes

# 50 lbs → kg（标准件单箱毛重上限）
FBA_MAX_STANDARD_GROSS_LB = 50.0
FBA_MAX_STANDARD_GROSS_KG = round(FBA_MAX_STANDARD_GROSS_LB * 0.45359237, 2)

# 25 inches → cm（单边长度上限）
FBA_MAX_SIDE_IN = 25.0
FBA_MAX_SIDE_CM = round(FBA_MAX_SIDE_IN * 2.54, 1)

# ---- S1e 判定口径（方案 v8 §3.4）：只按 kg/cm 判定，比较一律用“>”，计算用 Decimal ----
LB_TO_KG_EXACT = Decimal("0.45359237")
IN_TO_CM_EXACT = Decimal("2.54")
GROSS_BLOCK_KG = Decimal("22.68")   # 50 lb 的近似值，> 阻断（多件箱）
GROSS_WARN_KG = Decimal("22.5")     # > 预警
SIDE_BLOCK_CM = Decimal("63.5")     # 25 in，> 阻断（多件箱）
MECH_LIFT_KG = Decimal("45.36")     # 100 lb 的近似值，> 提示 Mechanical Lift

Number = Union[int, float, str, Decimal]


def to_decimal(v: Number) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if isinstance(v, bool):
        return Decimal(int(v))
    if isinstance(v, float):
        if not math.isfinite(v):
            raise ValueError(f"无法把 {v!r} 转成 Decimal")
        return Decimal(str(v))
    return Decimal(str(v))


def lb_to_kg_exact(lb: Number) -> Decimal:
    """lb → kg，精确系数，不取整。"""
    return to_decimal(lb) * LB_TO_KG_EXACT


def in_to_cm_exact(inch: Number) -> Decimal:
    """in → cm，精确系数，不取整。"""
    return to_decimal(inch) * IN_TO_CM_EXACT


def classify_box_weight(gross_kg: Number, single_oversize: bool = False) -> str:
    """返回 ok / warn / block / team_lift / mechanical_lift。"""
    g = to_decimal(gross_kg)
    if single_oversize:
        if g > MECH_LIFT_KG:
            return "mechanical_lift"
        if g > GROSS_BLOCK_KG:
            return "team_lift"
        return "ok"
    if g > GROSS_BLOCK_KG:
        return "block"
    if g > GROSS_WARN_KG:
        return "warn"
    return "ok"


def side_exceeds(side_cm: Number) -> bool:
    return to_decimal(side_cm) > SIDE_BLOCK_CM


_engine = PlacementFeeEngine()


def _sku_is_oversize(sku: SkuRow) -> bool:
    """外箱尺寸或重量分段判定为大件。"""
    sides = [sku.length_cm, sku.width_cm, sku.height_cm]
    if any(side_exceeds(s) for s in sides if s > 0):
        return True
    # v8：单件重量超过 22.68 kg（≈50 lb）不可能是标准件，直接算大件
    if sku.unit_weight_kg and to_decimal(sku.unit_weight_kg) > GROSS_BLOCK_KG:
        return True
    tier = _engine.classify_size_tier(
        sku.length_cm,
        sku.width_cm,
        sku.height_cm,
        sku.unit_weight_kg,
    )
    return tier in ("small_oversize", "large_oversize")


def _box_is_single_oversize_item(
    group: pd.DataFrame,
    sku_map: Dict[str, SkuRow],
    gross_kg: Optional[float] = None,
) -> bool:
    """单箱仅 1 件且属于超大件 SKU → 允许超过 50 lbs 标准上限。

    v8：箱内只有 1 件且箱重 > 22.68 kg 时，这件商品直接算大件。
    """
    total_qty = int(group["数量"].sum())
    if total_qty != 1 or group["SKU简称"].nunique() != 1:
        return False
    if gross_kg is not None and to_decimal(gross_kg) > GROSS_BLOCK_KG:
        return True
    sku_key = str(group.iloc[0]["SKU简称"]).strip()
    sku = sku_map.get(sku_key)
    return bool(sku and _sku_is_oversize(sku))


def _carrier_sku(group: pd.DataFrame, sku_map: Dict[str, SkuRow]) -> Optional[SkuRow]:
    """箱子的外箱 = 箱内体积最大的 SKU 箱规（与 box_metrics 承载箱口径一致）。"""
    best = None
    best_vol = -1.0
    for key in group["SKU简称"]:
        sku = sku_map.get(str(key).strip())
        if not sku:
            continue
        vol = sku.length_cm * sku.width_cm * sku.height_cm
        if vol > best_vol:
            best, best_vol = sku, vol
    return best


def _gross_by_box(metrics_df: pd.DataFrame) -> Dict[int, float]:
    if metrics_df is None or metrics_df.empty or "毛重(kg)" not in metrics_df.columns:
        return {}
    return {int(r["箱号"]): float(r["毛重(kg)"]) for _, r in metrics_df.iterrows()}


def check_box_side_violations(
    editor_df: pd.DataFrame,
    sku_rows: List[SkuRow],
    metrics_df: pd.DataFrame,
) -> List[Dict[str, Any]]:
    """多件箱外箱任一边 > 63.5 cm → 阻断；单件大件箱豁免。"""
    if editor_df is None or editor_df.empty:
        return []
    sku_map = {s.sku: s for s in sku_rows}
    gross = _gross_by_box(metrics_df)
    out: List[Dict[str, Any]] = []
    for box_no, group in editor_df.groupby("箱号"):
        bn = int(box_no)
        carrier = _carrier_sku(group, sku_map)
        if carrier is None:
            continue
        sides = [carrier.length_cm, carrier.width_cm, carrier.height_cm]
        max_side = max(sides)
        if not side_exceeds(max_side):
            continue
        if _box_is_single_oversize_item(group, sku_map, gross.get(bn)):
            continue
        out.append(
            {
                "box_no": bn,
                "max_side_cm": round(max_side, 2),
                "limit_cm": FBA_MAX_SIDE_CM,
                "message": (
                    f"箱 {bn} 外箱最长边 {max_side:.2f} cm 超过 FBA 上限 {FBA_MAX_SIDE_CM} cm (25 in)，"
                    f"多件箱不允许超边长"
                ),
            }
        )
    return out


def check_box_weight_notices(
    editor_df: pd.DataFrame,
    sku_rows: List[SkuRow],
    metrics_df: pd.DataFrame,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """返回 (预警列表 22.5<g≤22.68, 单件大件箱的 Team/Mechanical Lift 提示)。"""
    if metrics_df is None or metrics_df.empty or editor_df is None or editor_df.empty:
        return [], []
    sku_map = {s.sku: s for s in sku_rows}
    gross = _gross_by_box(metrics_df)
    warns: List[Dict[str, Any]] = []
    lifts: List[Dict[str, Any]] = []
    for box_no, group in editor_df.groupby("箱号"):
        bn = int(box_no)
        if bn not in gross:
            continue
        g = gross[bn]
        single = _box_is_single_oversize_item(group, sku_map, g)
        level = classify_box_weight(g, single)
        if level == "warn":
            warns.append(
                {
                    "box_no": bn,
                    "gross_kg": round(g, 3),
                    "message": f"箱 {bn} 毛重 {g:.2f} kg 接近 FBA 上限 {FBA_MAX_STANDARD_GROSS_KG} kg（预警线 22.5 kg）",
                }
            )
        elif level in ("team_lift", "mechanical_lift"):
            label = "Mechanical Lift" if level == "mechanical_lift" else "Team Lift"
            lifts.append(
                {
                    "box_no": bn,
                    "gross_kg": round(g, 3),
                    "label": label,
                    "message": f"箱 {bn} 为单件大件箱，毛重 {g:.2f} kg，请贴 {label} 标签",
                }
            )
    return warns, lifts


def check_carton_side_warnings(sku_rows: List[SkuRow]) -> List[Dict[str, Any]]:
    """Step1 外箱录入：任意单边超过 25 in (63.5 cm)。"""
    warnings: List[Dict[str, Any]] = []
    for sku in sku_rows:
        sides = {
            "长(cm)": sku.length_cm,
            "宽(cm)": sku.width_cm,
            "高(cm)": sku.height_cm,
        }
        max_side = max(sides.values()) if sides else 0.0
        if max_side <= FBA_MAX_SIDE_CM:
            continue
        over_side = max(sides, key=sides.get)
        warnings.append(
            {
                "sku": sku.sku,
                "side_label": over_side,
                "side_cm": round(sides[over_side], 1),
                "max_side_cm": round(max_side, 1),
                "limit_cm": FBA_MAX_SIDE_CM,
                "limit_in": FBA_MAX_SIDE_IN,
                "message": (
                    f"SKU {sku.sku} 外箱{over_side.replace('(cm)', '')} {sides[over_side]:.1f} cm "
                    f"超过 FBA 上限 {FBA_MAX_SIDE_CM} cm (25 in)，存在拒收风险"
                ),
            }
        )
    return warnings


def check_box_count_limit(editor_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """单票箱数超过亚马逊上限：需拆分货件，否则 STA 模板无法一次上传。"""
    if editor_df.empty:
        return None
    box_count = int(editor_df["箱号"].astype(int).max())
    limit = amazon_max_boxes()
    if box_count <= limit:
        return None
    return {
        "box_count": box_count,
        "limit": limit,
        "message": (
            f"当前方案共 {box_count} 箱，超过亚马逊单票上限 {limit} 箱，"
            f"需拆分为多个货件后再上传 Send to Amazon"
        ),
    }


def check_box_gross_violations(
    editor_df: pd.DataFrame,
    sku_rows: List[SkuRow],
    metrics_df: pd.DataFrame,
) -> List[Dict[str, Any]]:
    """单箱毛重超过 50 lbs；单件超大件豁免。"""
    if metrics_df.empty or editor_df.empty:
        return []

    sku_map = {s.sku: s for s in sku_rows}
    violations: List[Dict[str, Any]] = []

    for box_no, group in editor_df.groupby("箱号"):
        metric_row = metrics_df[metrics_df["箱号"] == box_no]
        if metric_row.empty:
            continue
        gross_kg = float(metric_row.iloc[0]["毛重(kg)"])
        if not to_decimal(gross_kg) > GROSS_BLOCK_KG:
            continue

        exempt = _box_is_single_oversize_item(group, sku_map, gross_kg)
        if exempt:
            continue

        violations.append(
            {
                "box_no": int(box_no),
                "gross_kg": round(gross_kg, 3),
                "limit_kg": FBA_MAX_STANDARD_GROSS_KG,
                "limit_lb": FBA_MAX_STANDARD_GROSS_LB,
                "exempt_oversize_single": False,
                "message": (
                    f"箱 {int(box_no)} 毛重 {gross_kg:.2f} kg 超过 FBA 标准件上限 "
                    f"{FBA_MAX_STANDARD_GROSS_KG} kg (50 lbs)；除非该箱仅装 1 个超大件"
                ),
            }
        )
    return violations


def enrich_metrics_with_fba_flags(
    editor_df: pd.DataFrame,
    sku_rows: List[SkuRow],
    metrics_df: pd.DataFrame,
) -> pd.DataFrame:
    """为每箱指标追加 FBA 合规标记列。"""
    if metrics_df.empty:
        return metrics_df

    sku_map = {s.sku: s for s in sku_rows}
    gross_flags: Dict[int, bool] = {}
    exempt_flags: Dict[int, bool] = {}

    gross_map = _gross_by_box(metrics_df)
    if not editor_df.empty:
        for box_no, group in editor_df.groupby("箱号"):
            bn = int(box_no)
            exempt = _box_is_single_oversize_item(group, sku_map, gross_map.get(bn))
            exempt_flags[bn] = exempt

    work = metrics_df.copy()
    fba_gross: List[bool] = []
    fba_exempt: List[bool] = []

    for _, row in work.iterrows():
        bn = int(row["箱号"])
        gross_kg = float(row["毛重(kg)"])
        over = to_decimal(gross_kg) > GROSS_BLOCK_KG and not exempt_flags.get(bn, False)
        gross_flags[bn] = over
        fba_gross.append(over)
        fba_exempt.append(exempt_flags.get(bn, False))

    work["FBA毛重违规"] = fba_gross
    work["FBA超大件豁免"] = fba_exempt
    return work


def evaluate_fba_boxing_compliance(
    editor_df: pd.DataFrame,
    sku_rows: List[SkuRow],
    metrics_df: pd.DataFrame,
) -> Dict[str, Any]:
    """汇总 FBA 物理红线：blocked = 存在不可豁免的毛重违规。"""
    side_warnings = check_carton_side_warnings(sku_rows)
    gross_violations = check_box_gross_violations(editor_df, sku_rows, metrics_df)
    side_violations = check_box_side_violations(editor_df, sku_rows, metrics_df)
    weight_warnings, lift_notices = check_box_weight_notices(editor_df, sku_rows, metrics_df)
    box_count_warning = check_box_count_limit(editor_df)

    summary: List[str] = []
    for w in side_warnings:
        summary.append(w["message"])
    for v in gross_violations:
        summary.append(v["message"])
    for v in side_violations:
        summary.append(v["message"])
    for w in weight_warnings:
        summary.append(w["message"])
    for n in lift_notices:
        summary.append(n["message"])
    if box_count_warning:
        summary.append(box_count_warning["message"])

    # 没有排箱数据时只提示不阻断；多件箱超重或超边长阻断
    blocked = len(gross_violations) > 0 or len(side_violations) > 0

    return {
        "blocked": blocked,
        "limits": {
            "max_standard_gross_kg": FBA_MAX_STANDARD_GROSS_KG,
            "max_standard_gross_lb": FBA_MAX_STANDARD_GROSS_LB,
            "max_side_cm": FBA_MAX_SIDE_CM,
            "max_side_in": FBA_MAX_SIDE_IN,
            "warn_gross_kg": float(GROSS_WARN_KG),
            "mechanical_lift_kg": float(MECH_LIFT_KG),
            "max_boxes_per_shipment": amazon_max_boxes(),
        },
        "carton_side_warnings": side_warnings,
        "box_gross_violations": gross_violations,
        "box_side_violations": side_violations,
        "box_weight_warnings": weight_warnings,
        "lift_notices": lift_notices,
        "box_count_warning": box_count_warning,
        "summary_lines": summary,
        "side_warning_count": len(side_warnings),
        "gross_violation_count": len(gross_violations),
        "side_violation_count": len(side_violations),
    }


def boxing_api_compliance(
    editor_df: pd.DataFrame,
    sku_rows: List[SkuRow],
    metrics_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """返回 (带 FBA 标记的 metrics, compliance 字典)。"""
    enriched = enrich_metrics_with_fba_flags(editor_df, sku_rows, metrics_df)
    compliance = evaluate_fba_boxing_compliance(editor_df, sku_rows, enriched)
    return enriched, compliance
