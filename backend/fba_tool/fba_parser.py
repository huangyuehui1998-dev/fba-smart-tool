from __future__ import annotations

import re
from typing import Dict

import pandas as pd

from fba_tool.forwarder_quote import build_forwarder_df
from fba_tool.shipment_parser import parse_csv_shipment
from fba_tool.template_loader import load_sku_mapping

COMMON_WAREHOUSES = [
    "FWA4", "ORF2", "GYR2", "SMF3", "RDU2", "IND9", "SBD1", "ONT8", "LGB8", "PHX6", "MDW2", "AVP1",
]
FACTORY_WAREHOUSE_ORDER = ["FWA4", "ORF2", "GYR2", "SMF3", "RDU2"]


def parse_amazon_csv(file_bytes: bytes, file_name: str = "") -> Dict[str, object]:
    ship = parse_csv_shipment(file_bytes, file_name=file_name)
    return {
        "warehouse_code": ship.warehouse_code,
        "shipment_id": ship.shipment_id,
        "box_count": ship.box_count,
        "box_items": ship.box_items,
        "box_specs": ship.box_specs,
        "box_data": ship.box_data,
        "column_to_box": ship.column_to_box,
    }


def build_factory_df(box_items_df: pd.DataFrame) -> pd.DataFrame:
    if box_items_df.empty:
        return pd.DataFrame(columns=["仓库代码", "纸箱编号", "产品名称", "数量"])
    df = box_items_df.copy()
    mapping = load_sku_mapping()
    df["产品名称"] = df["SKU"].apply(lambda s: simplify_sku(s, mapping))
    return df[["仓库代码", "箱号", "产品名称", "数量"]].rename(columns={"箱号": "纸箱编号"})


def simplify_sku(sku: str, mapping: Dict[str, str] | None = None) -> str:
    mapping = mapping or load_sku_mapping()
    if sku in mapping:
        return mapping[sku]
    pieces = [p for p in re.split(r"[-_]", str(sku)) if p]
    if len(pieces) >= 3:
        for i in range(len(pieces) - 1):
            if pieces[i].upper() in {"HUI", "GREY", "GRAY", "BLACK", "WHITE", "BEIGE", "BROWN", "ZHONG"}:
                return f"{pieces[i]}-{pieces[i + 1]}"
        return "-".join(pieces[-2:])
    return str(sku)
