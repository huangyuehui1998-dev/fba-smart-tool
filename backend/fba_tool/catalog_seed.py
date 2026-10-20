"""把产品信息表.csv 中「主库空」的报关字段一次性灌进 SQLite，不覆盖已有值。"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from fba_tool.master_db import get_product_by_sku, init_master_db, upsert_product
from fba_tool.product_catalog import load_product_catalog
from fba_tool.sku_keys import SkuCaseConflict

logger = logging.getLogger(__name__)
_LATIN_RE = re.compile(r"[A-Za-z]{2,}")


def _looks_english(text: str) -> bool:
    return bool(_LATIN_RE.search(text or ""))


def catalog_record_to_gap_payload(rec: Any) -> Dict[str, Any]:
    chinese = str(getattr(rec, "customs_name_cn", "") or getattr(rec, "chinese_name", "") or "").strip()
    product_name = str(getattr(rec, "product_name", "") or "").strip()
    payload: Dict[str, Any] = {
        "sku": str(getattr(rec, "sku", "") or "").strip(),
        "asin": str(getattr(rec, "asin", "") or "").strip(),
        "fnsku": str(getattr(rec, "fnsku", "") or "").strip(),
        "chinese_name": chinese,
        "hs_code": str(getattr(rec, "hs_code", "") or "").strip(),
        "material": str(getattr(rec, "material", "") or "").strip(),
        "declared_value": getattr(rec, "unit_cost", None),
        "data_source": "catalog_import",
    }
    if _looks_english(product_name):
        payload["english_name"] = product_name
    return payload


def import_catalog_gaps_into_master() -> Dict[str, int]:
    """overwrite=False：只填主库空字段。启动时调用；测试勿走这条路径。"""
    init_master_db()
    catalog = load_product_catalog()
    if not catalog or not catalog.records:
        return {"scanned": 0, "touched": 0}
    touched = 0
    scanned = 0
    for rec in catalog.records.values():
        payload = catalog_record_to_gap_payload(rec)
        sku = payload.get("sku") or ""
        if not sku:
            continue
        scanned += 1
        try:
            existing = get_product_by_sku(sku)
            if existing is None:
                upsert_product(payload, overwrite=False)
                touched += 1
                continue
            incoming = {k: v for k, v in payload.items() if k != "sku" and v not in (None, "")}
            if not incoming:
                continue
            upsert_product(payload, overwrite=False)
            touched += 1
        except SkuCaseConflict as exc:  # S9-step4-fix3：库里有只差大小写的多条 → 这一行不灌，其余照常
            logger.warning("catalog seed: 跳过 %s", exc)
    logger.info("catalog seed: scanned=%s touched=%s", scanned, touched)
    return {"scanned": scanned, "touched": touched}
