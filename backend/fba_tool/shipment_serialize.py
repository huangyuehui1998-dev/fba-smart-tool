"""CsvShipment 与 JSON 互转，供 Step 4 → Step 4.5 与 .fbox 持久化。"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from fba_tool.shipment_parser import CsvShipment, parse_csv_shipment


def csv_shipment_to_dict(ship: CsvShipment) -> Dict[str, Any]:
    box_fba_ids = {str(k): v for k, v in (ship.box_fba_ids or {}).items()}
    return {
        "shipment_id": ship.shipment_id,
        "warehouse_code": ship.warehouse_code,
        "box_count": ship.box_count,
        "box_items": ship.box_items.to_dict(orient="records") if not ship.box_items.empty else [],
        "box_specs": ship.box_specs.to_dict(orient="records") if not ship.box_specs.empty else [],
        "box_fba_ids": box_fba_ids,
        "sku_fnsku": dict(getattr(ship, "sku_fnsku", None) or {}),
        "warehouse_source": getattr(ship, "warehouse_source", "") or "",
    }


def csv_shipment_from_dict(data: Dict[str, Any] | None) -> Optional[CsvShipment]:
    if not data or not isinstance(data, dict):
        return None
    items = data.get("box_items") or []
    specs = data.get("box_specs") or []
    if not items and not specs:
        return None
    box_fba_raw = data.get("box_fba_ids") or {}
    box_fba_ids: Dict[int, str] = {}
    for k, v in box_fba_raw.items():
        try:
            box_fba_ids[int(k)] = str(v)
        except (TypeError, ValueError):
            continue
    sku_fnsku = {
        str(k).strip(): str(v).strip()
        for k, v in (data.get("sku_fnsku") or {}).items()
        if str(k).strip() and str(v).strip()
    }
    if not sku_fnsku:
        for rec in items:
            if not isinstance(rec, dict):
                continue
            sku = str(rec.get("SKU") or "").strip()
            fnsku = str(rec.get("FNSKU") or "").strip()
            if sku and fnsku:
                sku_fnsku[sku] = fnsku
    return CsvShipment(
        shipment_id=str(data.get("shipment_id") or "UNKNOWN").upper(),
        warehouse_code=str(data.get("warehouse_code") or "UNKN"),
        box_count=int(data.get("box_count") or 0),
        box_items=pd.DataFrame(items) if items else pd.DataFrame(columns=["仓库代码", "箱号", "SKU", "数量", "FNSKU"]),
        box_specs=pd.DataFrame(specs) if specs else pd.DataFrame(),
        box_fba_ids=box_fba_ids,
        sku_fnsku=sku_fnsku,
        warehouse_source=str(data.get("warehouse_source") or ""),
    )


def resolve_csv_shipment(
    *,
    parsed_shipment: Dict[str, Any] | None = None,
    csv_bytes: bytes | None = None,
    file_name: str = "",
) -> CsvShipment:
    if parsed_shipment:
        ship = csv_shipment_from_dict(parsed_shipment)
        if ship is not None and not ship.box_items.empty:
            return ship
    if csv_bytes:
        return parse_csv_shipment(csv_bytes, file_name=file_name, allow_unassigned_fba=True)
    raise ValueError("缺少货件数据：请传入 parsed_shipment 或 csv_base64")
