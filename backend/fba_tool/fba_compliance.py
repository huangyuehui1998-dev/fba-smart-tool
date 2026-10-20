"""亚马逊 FBA 入库纸箱物理红线校验（拒收 / Inbound Defect Fee 风险）。"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from fba_tool.models import SkuRow
from fba_tool.placement_fee import PlacementFeeEngine
from fba_tool.policy import (
    LTL,
    SPD_OWN,
    SPD_PARTNERED,
    dimension_blocked,
    fee_disclaimer,
    gross_block_kg,
    jewelry_block_kg,
    normalize_transport,
    other_side_limit_cm,
    result_source,
    rule,
    rule_value,
)

# 50 lbs → kg（标准件单箱毛重上限）
FBA_MAX_STANDARD_GROSS_LB = 50.0
FBA_MAX_STANDARD_GROSS_KG = round(FBA_MAX_STANDARD_GROSS_LB * 0.45359237, 2)

# 25 inches → cm（单边长度上限）
FBA_MAX_SIDE_IN = 25.0
FBA_MAX_SIDE_CM = round(FBA_MAX_SIDE_IN * 2.54, 1)

# ---- S1e 判定口径（方案 v8 §3.4）：只按 kg/cm 判定，比较一律用“>”，计算用 Decimal ----
LB_TO_KG_EXACT = Decimal("0.45359237")
IN_TO_CM_EXACT = Decimal("2.54")
GROSS_BLOCK_KG = gross_block_kg()   # 50 lb，> 阻断（多件箱）
GROSS_WARN_KG = Decimal("22.5")     # > 预警
SIDE_BLOCK_CM = other_side_limit_cm()  # 另两边 25 in
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


def _sku_is_oversize(sku: SkuRow, gross_kg: Optional[float] = None) -> bool:
    """用单品尺寸/重量判定超大件。单品尺寸缺失时，只有箱重 > 22.68kg 才算超大件。"""
    unit_l = float(getattr(sku, "unit_length_cm", 0) or 0)
    unit_w = float(getattr(sku, "unit_width_cm", 0) or 0)
    unit_h = float(getattr(sku, "unit_height_cm", 0) or 0)
    if unit_l > 0 and unit_w > 0 and unit_h > 0:
        if sku.unit_weight_kg and to_decimal(sku.unit_weight_kg) > GROSS_BLOCK_KG:
            return True
        tier = _engine.classify_size_tier(unit_l, unit_w, unit_h, sku.unit_weight_kg or 0)
        return tier in ("small_oversize", "large_oversize", "extra_large")
    if gross_kg is not None and to_decimal(gross_kg) > GROSS_BLOCK_KG:
        return True
    if sku.unit_weight_kg and to_decimal(sku.unit_weight_kg) > GROSS_BLOCK_KG:
        return True
    return False


def _box_is_single_oversize_item(
    group: pd.DataFrame,
    sku_map: Dict[str, SkuRow],
    gross_kg: Optional[float] = None,
) -> bool:
    """单箱仅 1 件且单品属于超大件 → 允许超过 50 lbs 标准上限。"""
    total_qty = int(group["数量"].sum())
    if total_qty != 1 or group["SKU简称"].nunique() != 1:
        return False
    sku_key = str(group.iloc[0]["SKU简称"]).strip()
    sku = sku_map.get(sku_key)
    if sku is None:
        return bool(gross_kg is not None and to_decimal(gross_kg) > GROSS_BLOCK_KG)
    return _sku_is_oversize(sku, gross_kg)


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
    destination: str = "FBA",
) -> List[Dict[str, Any]]:
    """多件箱：最长边 > 36in 或其余边 > 25in → 阻断；单件大件箱豁免。"""
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
        if not dimension_blocked(carrier.length_cm, carrier.width_cm, carrier.height_cm, destination):
            continue
        if destination.upper() != "AWD" and _box_is_single_oversize_item(group, sku_map, gross.get(bn)):
            continue
        sides = sorted([carrier.length_cm, carrier.width_cm, carrier.height_cm], reverse=True)
        out.append(
            {
                "box_no": bn,
                "max_side_cm": round(sides[0], 2),
                "limit_cm": float(other_side_limit_cm()),
                "source": result_source(rule("fba_multi_longest_in").get("source_type")),
                "message": (
                    f"箱 {bn} 外箱 {sides[0]:.2f}×{sides[1]:.2f}×{sides[2]:.2f} cm "
                    f"超过{destination}多件箱尺寸上限"
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
                    "source": "internal",
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
                    "source": "amazon",
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
        if not dimension_blocked(sku.length_cm, sku.width_cm, sku.height_cm, "FBA"):
            continue
        max_side = max(sides.values()) if sides else 0.0
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


def check_box_count_limit(
    editor_df: pd.DataFrame,
    transport_mode: str = SPD_PARTNERED,
) -> Optional[Dict[str, Any]]:
    """按运输方式检查单票箱数。自选承运人没有官方上限，只提示。"""
    mode = normalize_transport(transport_mode)
    if mode == SPD_OWN:
        entry = rule("boxes_spd_own")
        return {
            "box_count": int(editor_df["箱号"].astype(int).max()) if editor_df is not None and not editor_df.empty else 0,
            "limit": None,
            "level": "info",
            "source": "internal",
            "source_type": entry.get("source_type"),
            "message": "自选承运人小包裹箱数上限未找到官方出处，请以 STA 页面为准",
        }
    if editor_df is None or editor_df.empty:
        return None
    box_count = int(editor_df["箱号"].astype(int).max())
    if mode == LTL:
        entry = rule("boxes_ltl")
        limit = int(entry["value"])
        if box_count <= limit:
            return None
        return {
            "box_count": box_count,
            "limit": limit,
            "level": "block",
            "source": result_source(entry.get("source_type")),
            "source_type": entry.get("source_type"),
            "message": f"当前方案共 {box_count} 箱，超过 LTL/FTL 单票上限 {limit} 箱，不能继续导出",
        }
    entry = rule("boxes_spd_partnered")
    limit = int(entry["value"])
    if box_count <= limit:
        return None
    return {
        "box_count": box_count,
        "limit": limit,
        "level": "info",
        "source": result_source(entry.get("source_type")),
        "source_type": entry.get("source_type"),
        "message": f"当前方案共 {box_count} 箱，超过 SPD 合作承运人单票 {limit} 箱，请拆分货件后再上传",
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
                "source": "amazon",
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


def _policy_box_findings(
    editor_df: pd.DataFrame,
    sku_rows: List[SkuRow],
    metrics_df: pd.DataFrame,
) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    sku_map = {s.sku: s for s in sku_rows}
    unset = [s.sku for s in sku_rows if not str(getattr(s, "category", "") or "").strip()]
    if unset:
        findings.append(
            {
                "level": "info",
                "source": "internal",
                "message": f"{len(unset)} 个 SKU 未设品类",
            }
        )
    if editor_df is None or editor_df.empty:
        return findings
    gross = _gross_by_box(metrics_df)
    unit_limit = int(rule_value("max_units_per_box"))
    mixed_warn = int(rule_value("mixed_units_warn"))
    for box_no, group in editor_df.groupby("箱号"):
        bn = int(box_no)
        qty = int(group["数量"].sum())
        kinds = int(group["SKU简称"].nunique())
        if qty > unit_limit:
            entry = rule("max_units_per_box")
            findings.append(
                {
                    "box_no": bn,
                    "level": "block",
                    "source": result_source(entry.get("source_type")),
                    "source_type": entry.get("source_type"),
                    "message": f"箱 {bn} 共 {qty} 件，超过每箱 {unit_limit} 件上限",
                }
            )
        elif kinds > 1 and qty > mixed_warn:
            entry = rule("mixed_units_warn")
            findings.append(
                {
                    "box_no": bn,
                    "level": "warn",
                    "source": "internal",
                    "source_type": entry.get("source_type"),
                    "message": f"箱 {bn} 混装 {qty} 件，超过内部提示线 {mixed_warn} 件",
                }
            )
        cats = [
            str(getattr(sku_map.get(str(key).strip()), "category", "") or "").strip().lower()
            for key in group["SKU简称"]
        ]
        gross_kg = gross.get(bn)
        if gross_kg is not None and any(cat in {"jewelry", "watch"} for cat in cats):
            if to_decimal(gross_kg) > jewelry_block_kg():
                entry = rule("jewelry_watch_lb")
                findings.append(
                    {
                        "box_no": bn,
                        "level": "block",
                        "source": result_source(entry.get("source_type")),
                        "source_type": entry.get("source_type"),
                        "message": f"箱 {bn} 含珠宝或手表，毛重 {gross_kg:.2f} kg 超过 40lb",
                    }
                )
    return findings


def evaluate_fba_boxing_compliance(
    editor_df: pd.DataFrame,
    sku_rows: List[SkuRow],
    metrics_df: pd.DataFrame,
    transport_mode: str = SPD_PARTNERED,
    destination: str = "FBA",
) -> Dict[str, Any]:
    """汇总 FBA 物理红线：blocked = 存在不可豁免的毛重、尺寸或政策硬限制。"""
    side_warnings = check_carton_side_warnings(sku_rows)
    gross_violations = check_box_gross_violations(editor_df, sku_rows, metrics_df)
    side_violations = check_box_side_violations(editor_df, sku_rows, metrics_df, destination)
    weight_warnings, lift_notices = check_box_weight_notices(editor_df, sku_rows, metrics_df)
    box_count_warning = check_box_count_limit(editor_df, transport_mode)
    policy_findings = _policy_box_findings(editor_df, sku_rows, metrics_df)

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
    for finding in policy_findings:
        summary.append(finding["message"])
    if box_count_warning:
        summary.append(box_count_warning["message"])

    blocked = (
        len(gross_violations) > 0
        or len(side_violations) > 0
        or any(item.get("level") == "block" for item in policy_findings)
        or bool(box_count_warning and box_count_warning.get("level") == "block")
    )

    return {
        "blocked": blocked,
        "limits": {
            "max_standard_gross_kg": FBA_MAX_STANDARD_GROSS_KG,
            "max_standard_gross_lb": FBA_MAX_STANDARD_GROSS_LB,
            "max_side_cm": float(FBA_MAX_SIDE_CM),
            "max_side_in": FBA_MAX_SIDE_IN,
            "warn_gross_kg": float(GROSS_WARN_KG),
            "mechanical_lift_kg": float(MECH_LIFT_KG),
            "max_boxes_per_shipment": int(rule_value("boxes_spd_partnered")),
            "fee_disclaimer": fee_disclaimer(),
        },
        "policy_findings": policy_findings,
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
    transport_mode: str = SPD_PARTNERED,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """返回 (带 FBA 标记的 metrics, compliance 字典)。"""
    enriched = enrich_metrics_with_fba_flags(editor_df, sku_rows, metrics_df)
    compliance = evaluate_fba_boxing_compliance(
        editor_df, sku_rows, enriched, transport_mode=transport_mode
    )
    return enriched, compliance
