"""统一 FNSKU 解析：发货表 / 工人装箱单 / STA 导出共用。

优先级：
  1. 亚马逊 CSV（或 PDF）自带 FNSKU
  2. 本任务 Step 1 行 / fnsku_overrides
  3. SQLite 产品主库
  4. config/fnsku_mapping.json
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

from fba_tool.config_cache import load_json_cached
from fba_tool.sku_keys import lookup_sku


def normalize_fnsku(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"NAN", "NONE", "NULL"}:
        return ""
    return text


def fnsku_map_from_step1_rows(rows: Iterable[Mapping[str, Any]] | None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not rows:
        return out
    for row in rows:
        sku = str(row.get("SKU简称") or row.get("SKU") or "").strip()
        fnsku = normalize_fnsku(row.get("FNSKU") or row.get("fnsku") or "")
        if sku and fnsku:
            out[sku] = fnsku
    return out


def fnsku_map_from_csv_shipment(ship: Any | None) -> Dict[str, str]:
    if ship is None:
        return {}
    out: Dict[str, str] = {}
    extra = getattr(ship, "sku_fnsku", None) or {}
    if isinstance(extra, dict):
        for sku, fnsku in extra.items():
            key = str(sku or "").strip()
            val = normalize_fnsku(fnsku)
            if key and val:
                out[key] = val
    items = getattr(ship, "box_items", None)
    if items is not None and getattr(items, "empty", True) is False and "FNSKU" in getattr(items, "columns", []):
        for _, row in items.iterrows():
            sku = str(row.get("SKU") or "").strip()
            fnsku = normalize_fnsku(row.get("FNSKU") or "")
            if sku and fnsku:
                out.setdefault(sku, fnsku)
    return out


def fnsku_map_from_pairs(pairs: Iterable[Any] | None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not pairs:
        return out
    for pair in pairs:
        out.update(fnsku_map_from_csv_shipment(getattr(pair, "csv", None)))
        pdf = getattr(pair, "pdf", None)
        pages = getattr(pdf, "pages", None) if pdf is not None else None
        if pages:
            for page in pages:
                sku = str(getattr(page, "sku", "") or "").strip()
                fnsku = normalize_fnsku(getattr(page, "fnsku", "") or "")
                if sku and fnsku:
                    out.setdefault(sku, fnsku)
    return out


def load_json_fnsku_map() -> Dict[str, str]:
    base = load_json_cached("fnsku_mapping.json", {})
    if not isinstance(base, dict):
        return {}
    return {str(k).strip(): normalize_fnsku(v) for k, v in base.items() if str(k).strip() and normalize_fnsku(v)}


def load_master_fnsku_map() -> Dict[str, str]:
    from fba_tool.master_db import fnsku_mapping, init_master_db

    init_master_db()
    return {str(k).strip(): normalize_fnsku(v) for k, v in fnsku_mapping().items() if str(k).strip() and normalize_fnsku(v)}


def load_static_fnsku_map() -> Dict[str, str]:
    """json + 主库（主库覆盖 json）。不含产品信息表模糊匹配。"""
    return {**load_json_fnsku_map(), **load_master_fnsku_map()}


def build_fnsku_map(
    skus: Iterable[str],
    *,
    step1_map: Optional[Mapping[str, str]] = None,
    catalog: Any = None,
    json_map: Optional[Mapping[str, str]] = None,
    master_map: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """按 resolve_fnsku 的同一优先级批量解析一组 SKU（跳过第 1 级，Step 3 尚无 CSV）。

    Step 3 的内部留档/STA 必须与 Step 4 的发货表/工人单共用这条链，
    否则上传亚马逊的 FNSKU 会和工人手上贴标单印的不一致，导致贴错标无法入库。
    """
    if catalog is None:
        catalog = None
    master = master_map if master_map is not None else load_master_fnsku_map()
    mapping = json_map if json_map is not None else load_json_fnsku_map()
    step1 = step1_map or {}

    out: Dict[str, str] = {}
    for sku in skus:
        key = str(sku or "").strip()
        if not key or key in out:
            continue
        value = resolve_fnsku(
            key,
            step1_fnsku=lookup_sku(step1, key, "") or "",
            catalog=catalog,
            json_map=mapping,
            master_map=master,
        )
        if value:
            out[key] = value
    return out


def resolve_fnsku(
    sku: str,
    *,
    csv_fnsku: str = "",
    step1_fnsku: str = "",
    catalog: Any = None,
    json_map: Optional[Mapping[str, str]] = None,
    master_map: Optional[Mapping[str, str]] = None,
) -> str:
    key = str(sku or "").strip()
    direct = normalize_fnsku(csv_fnsku)
    if direct:
        return direct
    step1 = normalize_fnsku(step1_fnsku)
    if step1:
        return step1
    if not key:
        return ""

    master = master_map if master_map is not None else load_master_fnsku_map()
    # S9-step3：SKU 统一大小写 / 全角规则匹配；只差大小写的多个候选时不任选（返回空，后面会提示缺 FNSKU）
    master_val = normalize_fnsku(lookup_sku(master, key) or "")
    if master_val:
        return master_val

    if catalog is None:
        catalog = None
    rec = catalog.lookup(key) if catalog else None
    if rec and getattr(rec, "fnsku", ""):
        catalog_val = normalize_fnsku(rec.fnsku)
        if catalog_val:
            return catalog_val

    mapping = json_map if json_map is not None else load_json_fnsku_map()
    return normalize_fnsku(lookup_sku(mapping, key) or "")
