"""货代业务映射配置：forwarder_mapping.json（与 forwarders.json 模板元数据分离）。"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Dict, List, Optional

from fba_tool.app_paths import bundled_config_dir, resolve_config_read, resolve_config_write

_GROUP_LOGIC_VALUES = frozenset({"DETAIL_ROW", "GROUP_BY_BOX_RANGE", "GROUP_BY_SKU"})


def _default_path():
    return bundled_config_dir() / "forwarder_mapping.default.json"


def _user_path():
    return resolve_config_read("forwarder_mapping.json")


def _write_path():
    return resolve_config_write("forwarder_mapping.json")


def load_forwarder_mapping_config() -> Dict[str, Any]:
    path = _user_path()
    if not path.is_file():
        default = _default_path()
        if default.is_file():
            return json.loads(default.read_text(encoding="utf-8"))
        return {"version": 1, "global_table_column_aliases": {}, "forwarders": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "global_table_column_aliases": {}, "forwarders": {}}


def get_forwarder_mapping(forwarder_id: str) -> Optional[Dict[str, Any]]:
    cfg = load_forwarder_mapping_config()
    entry = (cfg.get("forwarders") or {}).get(forwarder_id)
    if not isinstance(entry, dict):
        return None
    return entry


def merge_table_column_aliases(
    forwarder_id: str | None = None,
    extra_cfg: dict | None = None,
) -> Dict[str, List[str]]:
    """合并 global + 货代 + invoice_mapping 扩展别名（替代硬编码 TABLE_COLUMN_ALIASES）。"""
    from fba_tool.invoice_automation import load_invoice_config

    mapping_cfg = load_forwarder_mapping_config()
    merged: Dict[str, List[str]] = {}
    for key, aliases in (mapping_cfg.get("global_table_column_aliases") or {}).items():
        merged[key] = list(aliases)

    if forwarder_id:
        fwd = get_forwarder_mapping(forwarder_id) or {}
        for key, aliases in (fwd.get("table_column_aliases") or {}).items():
            merged.setdefault(key, [])
            for alias in aliases:
                if alias not in merged[key]:
                    merged[key].append(alias)

    inv_cfg = extra_cfg if extra_cfg is not None else load_invoice_config()
    for key, aliases in (inv_cfg.get("table_column_aliases") or {}).items():
        merged.setdefault(key, [])
        for alias in aliases:
            if alias not in merged[key]:
                merged[key].append(alias)

    return merged


def normalize_group_logic(value: str | None) -> str:
    text = str(value or "DETAIL_ROW").strip().upper()
    if text in _GROUP_LOGIC_VALUES:
        return text
    if text == "GROUP_BY_BOX_RANGE":
        return "GROUP_BY_BOX_RANGE"
    return "DETAIL_ROW"


def list_forwarders_enriched() -> List[Dict[str, Any]]:
    """合并 forwarders.json（UI/模板）与 forwarder_mapping.json（业务逻辑）。"""
    from fba_tool.forwarder_registry import list_forwarders

    mapping_cfg = load_forwarder_mapping_config()
    mapping_fwd = mapping_cfg.get("forwarders") or {}
    out: List[Dict[str, Any]] = []
    for profile in list_forwarders():
        row = profile.to_dict()
        biz = mapping_fwd.get(profile.id)
        if isinstance(biz, dict):
            row["group_logic"] = normalize_group_logic(biz.get("group_logic"))
            row["unit_conversion"] = biz.get("unit_conversion") or {}
            row["columns_mapping"] = biz.get("columns_mapping") or {}
            row["has_mapping_engine"] = True
        else:
            row["group_logic"] = "DETAIL_ROW"
            row["unit_conversion"] = {}
            row["columns_mapping"] = {}
            row["has_mapping_engine"] = False
        out.append(row)
    return out


def ensure_forwarder_mapping_seeded() -> None:
    """首次运行：从出厂默认复制 forwarder_mapping.json。"""
    user = _write_path()
    if user.is_file():
        return
    default = _default_path()
    if not default.is_file():
        return
    user.parent.mkdir(parents=True, exist_ok=True)
    user.write_text(default.read_text(encoding="utf-8"), encoding="utf-8")
