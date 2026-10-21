"""渠道体积重除数和商品级分段政策。容差标 internal，可改配置。"""
from __future__ import annotations

import json
from decimal import Decimal
from functools import lru_cache
from typing import Any, Dict

from fba_tool.app_paths import resolve_config_read


def _load(name: str) -> Dict[str, Any]:
    path = resolve_config_read(name)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def forwarder_registry() -> Dict[str, Any]:
    return _load("forwarder_registry.json")


@lru_cache(maxsize=1)
def item_policy() -> Dict[str, Any]:
    data = _load("item_size_policy.json")
    data.setdefault("reimbursement_window_days", 90)
    data.setdefault("source_type", "amazon_forum")
    data.setdefault("effective_date", None)
    data.setdefault("verified_at", "2026-10-20")
    data.setdefault("cross_tier_margin_pct", 3)
    data.setdefault("next_weight_boundary_kg", "0.45359237")
    data.setdefault("remeasure_guide", "")
    data.setdefault("reimbursement_text", "可能多收费，请在 90 天内申请报销")
    return data


def _entry(measured_by: str) -> Dict[str, Any]:
    registry = forwarder_registry()
    for entry in registry.values():
        if entry.get("measured_by") == measured_by:
            return entry
    if measured_by in {"forwarder_send", "send"}:
        return registry.get("send") or {}
    return registry.get("jiufang") or {"dim_divisor": 6000, "source_label": "forwarder"}


def dim_divisor(measured_by: str = "forwarder_jiufang") -> Decimal:
    return Decimal(str(_entry(measured_by).get("dim_divisor") or 6000))


def source_label(measured_by: str = "forwarder_jiufang") -> str:
    return str(_entry(measured_by).get("source_label") or "forwarder")
