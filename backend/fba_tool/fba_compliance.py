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
    gross_warn_kg,
    jewelry_block_kg,
    mech_lift_kg,
    normalize_transport,
    other_side_limit_cm,
    pending_notes,
    result_source,
    rule,
    rule_value,
    single_oversize_max_kg,
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
# 动态获取当前配置阈值（热重载即时生效）
def current_gross_block_kg() -> Decimal:
    return gross_block_kg()

def current_gross_warn_kg() -> Decimal:
    return gross_warn_kg()

def current_side_block_cm() -> Decimal:
    return other_side_limit_cm()

def current_mech_lift_kg() -> Decimal:
    return mech_lift_kg()

BULKY_TIERS = frozenset({"small_oversize", "large_oversize", "extra_large"})

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
        if g > current_mech_lift_kg():
            return "mechanical_lift"
        if g > current_gross_block_kg():
            return "team_lift"
        return "ok"
    if g > current_gross_block_kg():
        return "block"
    if g > current_gross_warn_kg():
        return "warn"
    return "ok"


def side_exceeds(side_cm: Number) -> bool:
    return to_decimal(side_cm) > current_side_block_cm()


_engine = PlacementFeeEngine()


def _unit_tier(sku: Optional[SkuRow]) -> Optional[str]:
    """有完整单品包装尺寸时才分段。缺尺寸不算 Small/Large Bulky 或 Extra-large。"""
    if sku is None:
        return None
    unit_l = float(getattr(sku, "unit_length_cm", 0) or 0)
    unit_w = float(getattr(sku, "unit_width_cm", 0) or 0)
    unit_h = float(getattr(sku, "unit_height_cm", 0) or 0)
    if unit_l <= 0 or unit_w <= 0 or unit_h <= 0:
        return None
    return _engine.classify_size_tier(unit_l, unit_w, unit_h, float(sku.unit_weight_kg or 0))


def _unit_over_50(sku: Optional[SkuRow]) -> bool:
    if sku is None or not sku.unit_weight_kg:
        return False
    return to_decimal(sku.unit_weight_kg) > current_gross_block_kg()


def _sku_is_oversize(sku: SkuRow, gross_kg: Optional[float] = None) -> bool:
    """单品尺寸段为 Bulky/Extra-large，或单件重量超过 50 lb。缺尺寸时不靠箱重推断。"""
    del gross_kg
    if _unit_tier(sku) in BULKY_TIERS:
        return True
    return _unit_over_50(sku)


def _single_sku(group: pd.DataFrame, sku_map: Dict[str, SkuRow]) -> Optional[SkuRow]:
    total_qty = int(group["数量"].sum())
    if total_qty != 1 or group["SKU简称"].nunique() != 1:
        return None
    return sku_map.get(str(group.iloc[0]["SKU简称"]).strip())


def _box_is_single_oversize_item(
    group: pd.DataFrame,
    sku_map: Dict[str, SkuRow],
    gross_kg: Optional[float] = None,
) -> bool:
    """恰好 1 件，且尺寸段为 Small Bulky、Large Bulky 或 Extra-large。"""
    del gross_kg
    return _unit_tier(_single_sku(group, sku_map)) in BULKY_TIERS


def _inches(cm: Number) -> Decimal:
    return to_decimal(cm) / IN_TO_CM_EXACT


def _sorted_inches(length_cm: Number, width_cm: Number, height_cm: Number) -> Tuple[Decimal, Decimal, Decimal]:
    sides = sorted((_inches(length_cm), _inches(width_cm), _inches(height_cm)), reverse=True)
    return sides[0], sides[1], sides[2]


def _scan_boxes(
    editor_df: pd.DataFrame,
    sku_rows: List[SkuRow],
    metrics_df: pd.DataFrame,
    destination: str = "FBA",
) -> List[Dict[str, Any]]:
    if editor_df is None or editor_df.empty:
        return []
    sku_map = {s.sku: s for s in sku_rows}
    gross = _gross_by_box(metrics_df)
    longest_limit = to_decimal(rule_value("single_oversize_exemption_in", 25.0))
    longer_slack = to_decimal(rule_value("cushion_max_slack_in", 2.0))
    limit_65 = single_oversize_max_kg()
    limit_100 = mech_lift_kg()
    awd = str(destination or "FBA").upper() == "AWD"
    out: List[Dict[str, Any]] = []
    for box_no, group in editor_df.groupby("箱号"):
        try:
            bn = int(box_no)
        except (ValueError, TypeError):
            bn = 0
        carrier = _carrier_sku(group, sku_map)
        sku = _single_sku(group, sku_map)
        tier = _unit_tier(sku)
        single_bulky = tier in BULKY_TIERS
        item_over_50 = _unit_over_50(sku)
        item_longest = None
        if sku is not None and tier is not None:
            item_longest = _sorted_inches(sku.unit_length_cm, sku.unit_width_cm, sku.unit_height_cm)[0]
        over_dim = False
        box_longest = None
        sides_cm: List[float] = []
        if carrier is not None:
            sides_cm = sorted([carrier.length_cm, carrier.width_cm, carrier.height_cm], reverse=True)
            box_longest = _sorted_inches(carrier.length_cm, carrier.width_cm, carrier.height_cm)[0]
            over_dim = dimension_blocked(carrier.length_cm, carrier.width_cm, carrier.height_cm, destination)
        
        # 单件装箱判定：箱内商品总件数必须严格为 1，且仅有 1 个 SKU
        total_box_qty = int(pd.to_numeric(group["数量"], errors="coerce").fillna(0).sum()) if "数量" in group.columns else 0
        sku_unique_count = group["SKU简称"].nunique() if "SKU简称" in group.columns else 1
        single_box = bool(total_box_qty == 1 and sku_unique_count == 1)

        # 单件大件豁免条件 C：仅单箱单件大件商品时豁免；若单品净尺寸缺失则柔性降级放行（不硬阻断）
        if single_box:
            if item_longest is not None:
                condition_c = bool(item_longest > longest_limit or single_bulky)
            else:
                condition_c = bool(box_longest is not None and box_longest > longest_limit)
        else:
            condition_c = False

        g = to_decimal(gross[bn]) if bn in gross else None
        over_50 = g is not None and g > current_gross_block_kg()
        over_65 = g is not None and g > limit_65
        over_100 = g is not None and g > limit_100
        within = not over_dim
        pending_overlay = bool(condition_c and item_over_50 and over_dim and over_50)

        # AWD 仓库严格禁止单件大件豁免，超过 25 in 必须硬阻断；FBA 仓库在符合 condition_c 时豁免
        # 若外箱次长边 > 25 in 且单品次长边 <= 25 in，则外箱次长边不可豁免，必须阻断
        box_second = _sorted_inches(carrier.length_cm, carrier.width_cm, carrier.height_cm)[1] if carrier else None
        item_second = _sorted_inches(sku.unit_length_cm, sku.unit_width_cm, sku.unit_height_cm)[1] if (sku and tier) else None
        side_two_unexempt = bool(box_second is not None and box_second > 25.0 and (item_second is None or item_second <= 25.0))
        dim_blocked = bool(over_dim and (awd or not condition_c or side_two_unexempt))
        weight_blocked = False
        lift = None

        if g is not None:
            if awd and over_50:
                # AWD 仓库禁止单箱毛重超过 50 lb，无大件重量豁免
                weight_blocked = True
            elif pending_overlay or item_over_50:
                if over_100:
                    lift = "Mechanical Lift"
                elif over_50:
                    lift = "Team Lift"
            elif single_bulky or condition_c:
                if over_100:
                    lift = "Mechanical Lift"
                elif over_65:
                    weight_blocked = True
                elif over_50:
                    lift = "Team Lift"
            elif over_50:
                weight_blocked = True

        internal = bool(
            g is not None
            and not single_bulky
            and not item_over_50
            and not weight_blocked
            and g > current_gross_warn_kg()
        )
        longer = bool(
            condition_c
            and box_longest is not None
            and item_longest is not None
            and box_longest - item_longest > longer_slack
        )
        exempt = bool(over_50 and not weight_blocked and (item_over_50 or single_bulky or pending_overlay))
        out.append(
            {
                "box_no": bn,
                "gross_kg": float(g) if g is not None else None,
                "sides_cm": sides_cm,
                "dim_blocked": dim_blocked,
                "weight_blocked": weight_blocked,
                "weight_over_65": bool(weight_blocked and over_65),
                "internal_warn": internal,
                "lift": lift,
                "longer_than_item": longer,
                "pending_overlay": pending_overlay,
                "awd": awd and (over_dim or over_50),
                "awd_weight": bool(awd and over_50),
                "exempt": exempt,
                "single_box": single_box,
                "condition_c": condition_c,
            }
        )
    return out


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


def _gross_by_box(metrics_df: pd.DataFrame) -> Dict[Any, float]:
    if metrics_df is None or metrics_df.empty or "毛重(kg)" not in metrics_df.columns:
        return {}
    res: Dict[Any, float] = {}
    for _, r in metrics_df.iterrows():
        b = r.get("箱号")
        try:
            k = int(b)
        except (ValueError, TypeError):
            k = str(b).strip() if b is not None else ""
        try:
            res[k] = float(r["毛重(kg)"])
        except (ValueError, TypeError):
            pass
    return res


def _fmt_sides(sides: List[float]) -> str:
    if len(sides) < 3:
        return ""
    return f"{sides[0]:.2f}×{sides[1]:.2f}×{sides[2]:.2f}"


def check_box_side_violations(
    editor_df: pd.DataFrame,
    sku_rows: List[SkuRow],
    metrics_df: pd.DataFrame,
    destination: str = "FBA",
) -> List[Dict[str, Any]]:
    """多件箱超出 36×25×25 in 阻断。单件超大且商品最长边 >36 in 时放宽尺寸。"""
    out: List[Dict[str, Any]] = []
    for row in _scan_boxes(editor_df, sku_rows, metrics_df, destination):
        if not row["dim_blocked"]:
            continue
        sides = row["sides_cm"]
        if row["awd"]:
            entry = rule("awd_box_side_in")
            message = (
                f"箱 {row['box_no']} 外箱 {_fmt_sides(sides)} cm 超过 AWD 25×25×25 in。待核实。"
            )
        else:
            entry = rule("fba_multi_longest_in")
            message = (
                f"箱 {row['box_no']} 外箱 {_fmt_sides(sides)} cm 超过多件箱尺寸上限 36×25×25 in"
            )
        out.append(
            {
                "box_no": row["box_no"],
                "max_side_cm": round(sides[0], 2) if sides else None,
                "limit_cm": float(other_side_limit_cm()),
                "source": result_source(entry.get("source_type")),
                "source_type": entry.get("source_type"),
                "message": message,
            }
        )
    return out


def check_box_weight_notices(
    editor_df: pd.DataFrame,
    sku_rows: List[SkuRow],
    metrics_df: pd.DataFrame,
    destination: str = "FBA",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """返回 (内部余量预警, Team/Mechanical Lift)。单件超大箱不触发 22.5kg 预警。"""
    warns: List[Dict[str, Any]] = []
    lifts: List[Dict[str, Any]] = []
    for row in _scan_boxes(editor_df, sku_rows, metrics_df, destination):
        g = row["gross_kg"]
        if g is None:
            continue
        bn = row["box_no"]
        if row["internal_warn"]:
            warns.append(
                {
                    "box_no": bn,
                    "gross_kg": round(g, 3),
                    "source": "internal",
                    "source_type": "internal",
                    "message": f"箱 {bn} 毛重 {g:.2f} kg 超过内部余量 22.5kg",
                }
            )
        if row["lift"]:
            label = row["lift"]
            pending = "待核实。" if row["pending_overlay"] else ""
            msg = (
                f"箱 {bn} 毛重 {g:.2f} kg，超过 100 lb，须在顶部及 4 个侧面共贴 5 张 Mechanical Lift 标签。{pending}"
                if label == "Mechanical Lift"
                else f"箱 {bn} 毛重 {g:.2f} kg，超过 50 lb，须在顶部及 4 个侧面共贴 5 张 Team Lift 标签。{pending}"
            )
            lifts.append(
                {
                    "box_no": bn,
                    "gross_kg": round(g, 3),
                    "label": label,
                    "source": "pending" if row["pending_overlay"] else "amazon",
                    "source_type": "pending_verification" if row["pending_overlay"] else "amazon_official",
                    "pending_verification": bool(row["pending_overlay"]),
                    "message": msg,
                }
            )
    return warns, lifts


def check_box_fit_warnings(
    editor_df: pd.DataFrame,
    sku_rows: List[SkuRow],
    metrics_df: pd.DataFrame,
    destination: str = "FBA",
) -> List[Dict[str, Any]]:
    """箱子最长边比商品长出的英寸数超过内部阈值时提示，不阻断。"""
    out: List[Dict[str, Any]] = []
    entry = rule("box_longer_than_item_in")
    for row in _scan_boxes(editor_df, sku_rows, metrics_df, destination):
        if not row["longer_than_item"]:
            continue
        out.append(
            {
                "box_no": row["box_no"],
                "level": "warn",
                "source": "internal",
                "source_type": entry.get("source_type"),
                "message": f"箱 {row['box_no']} 箱子明显长于商品（外箱长于商品超过 2 英寸），请确认包装缓冲衬垫厚度 ≤ 2 英寸，避免入库缺陷费",
            }
        )
    return out


def check_carton_side_warnings(sku_rows: List[SkuRow]) -> List[Dict[str, Any]]:
    """Step1 外箱录入：超出多件箱 36×25×25 in。"""
    warnings: List[Dict[str, Any]] = []
    for sku in sku_rows:
        sides = {
            "长(cm)": sku.length_cm,
            "宽(cm)": sku.width_cm,
            "高(cm)": sku.height_cm,
        }
        if not dimension_blocked(sku.length_cm, sku.width_cm, sku.height_cm, "FBA"):
            continue
        tier = _unit_tier(sku)
        if tier in BULKY_TIERS:
            item_longest = _sorted_inches(sku.unit_length_cm, sku.unit_width_cm, sku.unit_height_cm)[0]
            if item_longest > to_decimal(rule_value("fba_multi_longest_in")):
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
                    f"超过多件箱尺寸上限 25×25×25 in（63.5cm），存在拒收风险"
                ),
            }
        )
    return warnings


def _calc_box_count(editor_df: pd.DataFrame) -> int:
    """安全计算箱数，使用 nunique 防御离散箱号，空值/字符串脏数据优雅回退。"""
    if editor_df is None or editor_df.empty or "箱号" not in editor_df.columns:
        return 0
    s = pd.to_numeric(editor_df["箱号"], errors="coerce").dropna()
    if not s.empty:
        return int(s.nunique())
    return int(editor_df["箱号"].astype(str).str.strip().nunique())


def check_box_count_limit(
    editor_df: pd.DataFrame,
    transport_mode: str = SPD_PARTNERED,
) -> Optional[Dict[str, Any]]:
    """按运输方式检查单票箱数。自选承运人上限 500 箱，合作承运人 200 箱，LTL 5000 箱。"""
    if editor_df is None or editor_df.empty:
        return None
    box_count = _calc_box_count(editor_df)
    mode = normalize_transport(transport_mode)
    if mode == SPD_OWN:
        entry = rule("boxes_spd_own")
        limit = int(entry.get("value") or 500)
        if box_count <= limit:
            return None
        return {
            "box_count": box_count,
            "limit": limit,
            "level": "warn",
            "source": result_source(entry.get("source_type")),
            "source_type": entry.get("source_type"),
            "message": f"当前方案共 {box_count} 箱，超过自选承运人单票建议上限 {limit} 箱，请核实 Send to Amazon 页面要求并考虑拆分货件",
        }
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
    destination: str = "FBA",
) -> List[Dict[str, Any]]:
    """超过 50 lb 或单件超大箱超过 65 lb 时阻断。AWD 仓库超过 50 lb 严禁入库。"""
    if metrics_df is None or metrics_df.empty or editor_df is None or editor_df.empty:
        return []
    violations: List[Dict[str, Any]] = []
    for row in _scan_boxes(editor_df, sku_rows, metrics_df, destination):
        if not row["weight_blocked"] or row["gross_kg"] is None:
            continue
        gross_kg = float(row["gross_kg"])
        if row.get("awd_weight"):
            entry = rule("awd_max_weight_lb")
            message = f"箱 {row['box_no']} 毛重 {gross_kg:.2f} kg 超过 AWD 仓库上限 50 lb（22.68kg），AWD 严禁超重箱"
        elif row["weight_over_65"]:
            entry = rule("single_oversize_max_lb")
            message = f"箱 {row['box_no']} 毛重 {gross_kg:.2f} kg 超过 65 lb（29.48kg）上限"
        else:
            entry = rule("multi_box_weight_lb")
            message = f"箱 {row['box_no']} 毛重 {gross_kg:.2f} kg 超过亚马逊 50 lb（22.68kg）上限"
        violations.append(
            {
                "box_no": row["box_no"],
                "gross_kg": gross_kg,
                "source": result_source(entry.get("source_type")),
                "source_type": entry.get("source_type"),
                "message": message,
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

    decisions = {row["box_no"]: row for row in _scan_boxes(editor_df, sku_rows, metrics_df)}
    work = metrics_df.copy()
    fba_gross: List[bool] = []
    fba_exempt: List[bool] = []

    for _, row in work.iterrows():
        bn = int(row["箱号"])
        decision = decisions.get(bn) or {}
        fba_gross.append(bool(decision.get("weight_blocked")))
        fba_exempt.append(bool(decision.get("exempt")))

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
    gross_violations = check_box_gross_violations(editor_df, sku_rows, metrics_df, destination)
    side_violations = check_box_side_violations(editor_df, sku_rows, metrics_df, destination)
    weight_warnings, lift_notices = check_box_weight_notices(editor_df, sku_rows, metrics_df, destination)
    fit_warnings = check_box_fit_warnings(editor_df, sku_rows, metrics_df, destination)
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
    for w in fit_warnings:
        summary.append(w["message"])
    for note in pending_notes():
        summary.append(note)
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
            "warn_gross_kg": float(current_gross_warn_kg()),
            "mechanical_lift_kg": float(current_mech_lift_kg()),
            "single_oversize_max_kg": float(single_oversize_max_kg()),
            "max_longest_in": float(rule_value("fba_multi_longest_in")),
            "max_other_side_in": float(rule_value("fba_multi_other_side_in")),
            "max_boxes_per_shipment": int(rule_value("boxes_spd_partnered")),
            "fee_disclaimer": fee_disclaimer(),
        },
        "policy_findings": policy_findings,
        "carton_side_warnings": side_warnings,
        "box_gross_violations": gross_violations,
        "box_side_violations": side_violations,
        "box_weight_warnings": weight_warnings,
        "box_fit_warnings": fit_warnings,
        "lift_notices": lift_notices,
        "pending_notes": pending_notes(),
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


def __getattr__(name: str):
    if name == "GROSS_BLOCK_KG":
        return current_gross_block_kg()
    if name == "GROSS_WARN_KG":
        return current_gross_warn_kg()
    if name == "SIDE_BLOCK_CM":
        return current_side_block_cm()
    if name == "MECH_LIFT_KG":
        return current_mech_lift_kg()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
