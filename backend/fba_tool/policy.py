"""入库规则。用户 app_data/config/policy.json 优先于出厂 policy.default.json。"""
from __future__ import annotations

import json
from decimal import Decimal
from functools import lru_cache
from typing import Any, Dict, List, Optional

from fba_tool.app_paths import resolve_config_read

LB_TO_KG = Decimal("0.45359237")
IN_TO_CM = Decimal("2.54")

SPD_PARTNERED = "spd_partnered"
SPD_OWN = "spd_own"
LTL = "ltl"
TRANSPORT_MODES = (SPD_PARTNERED, SPD_OWN, LTL)


def _dec(value: Any) -> Decimal:
    return Decimal(str(value))


@lru_cache(maxsize=1)
def load_policy() -> Dict[str, Any]:
    path = resolve_config_read("policy.json")
    return json.loads(path.read_text(encoding="utf-8"))


def rule(key: str) -> Dict[str, Any]:
    found = load_policy()["rules"][key]
    return dict(found)


def rule_value(key: str) -> Any:
    return rule(key).get("value")


def inches_to_cm(inches: Any) -> Decimal:
    return _dec(inches) * IN_TO_CM


def pounds_to_kg(pounds: Any) -> Decimal:
    return _dec(pounds) * LB_TO_KG


def result_source(source_type: Optional[str]) -> str:
    """合规结果标签：官方或亚马逊论坛算亚马逊，未核实的出处单独标出。"""
    if source_type in ("official", "amazon_official", "amazon_official_derived", "amazon_forum"):
        return "amazon"
    if source_type == "pending_verification":
        return "pending"
    return "internal"


def pending_notes() -> List[str]:
    """未核实规则的界面文案。每条都带“待核实”，不作为阻断依据。"""
    policy = load_policy()
    notes: List[str] = []
    for entry in policy.get("rules", {}).values():
        if not isinstance(entry, dict) or entry.get("source_type") != "pending_verification":
            continue
        text = str(entry.get("note") or "").strip()
        if text and "待核实" not in text:
            text = f"{text} 待核实"
        if text:
            notes.append(text)
    for entry in policy.get("unverified", {}).values():
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("note") or "").strip()
        if text and "待核实" not in text:
            text = f"{text} 待核实"
        if text:
            notes.append(text)
    return notes


def longest_limit_cm() -> Decimal:
    return inches_to_cm(rule_value("fba_multi_longest_in"))


def other_side_limit_cm() -> Decimal:
    return inches_to_cm(rule_value("fba_multi_other_side_in"))


def awd_side_limit_cm() -> Decimal:
    return inches_to_cm(rule_value("awd_box_side_in"))


def gross_block_kg() -> Decimal:
    return pounds_to_kg(rule_value("multi_box_weight_lb")).quantize(Decimal("0.01"))


def gross_warn_kg() -> Decimal:
    return _dec(rule_value("multi_box_weight_warn_kg"))


def single_oversize_max_kg() -> Decimal:
    return pounds_to_kg(rule_value("single_oversize_max_lb")).quantize(Decimal("0.01"))


def mech_lift_kg() -> Decimal:
    return pounds_to_kg(rule_value("mech_lift_lb")).quantize(Decimal("0.01"))


def jewelry_block_kg() -> Decimal:
    return pounds_to_kg(rule_value("jewelry_watch_lb"))


def low_multi_box_kg() -> Decimal:
    return pounds_to_kg(rule_value("low_multi_box_lb"))


def size_limits() -> Dict[str, Dict[str, float]]:
    return load_policy()["size_limits_in"]


def placement_classes() -> Dict[str, List[Dict[str, Any]]]:
    return load_policy()["placement_fees"]["classes"]


def fee_disclaimer() -> str:
    return str(load_policy().get("fee_disclaimer") or "")


def map_category_name(raw: Any) -> Optional[str]:
    """领星品类名 → jewelry / watch / other。映射不到返回 None，不触发 40lb。"""
    text = str(raw or "").strip()
    if not text:
        return None
    path = resolve_config_read("category_map.json")
    table = json.loads(path.read_text(encoding="utf-8")).get("map") or {}
    if text in table:
        return table[text]
    lowered = text.lower()
    for key, value in table.items():
        if str(key).lower() == lowered:
            return value
    if lowered in {"jewelry", "watch", "other"}:
        return lowered
    return None


def dimension_blocked(length_cm: float, width_cm: float, height_cm: float, destination: str = "FBA") -> bool:
    sides = sorted((_dec(length_cm), _dec(width_cm), _dec(height_cm)), reverse=True)
    if str(destination or "FBA").upper() == "AWD":
        limit = awd_side_limit_cm()
        return any(side > limit for side in sides)
    longest, second, third = sides
    return longest > longest_limit_cm() or second > other_side_limit_cm() or third > other_side_limit_cm()


def normalize_transport(mode: Optional[str]) -> str:
    text = str(mode or SPD_PARTNERED).strip().lower().replace("-", "_")
    aliases = {
        "spd_partnered": SPD_PARTNERED,
        "spd_合作承运人": SPD_PARTNERED,
        "partnered": SPD_PARTNERED,
        "spd_own": SPD_OWN,
        "spd_自选承运人": SPD_OWN,
        "own": SPD_OWN,
        "ltl": LTL,
        "ltl_ftl": LTL,
        "ftl": LTL,
    }
    return aliases.get(text, SPD_PARTNERED)
