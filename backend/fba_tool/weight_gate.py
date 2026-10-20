"""导出前的毛重确认门禁。未确认且存在 requires_confirm 时返回 409。"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from fba_tool.boxing import box_metrics, dataframe_to_sku_rows
from fba_tool.data_processing import check_gross_weight_consistency, with_computed_columns
from fba_tool.user_config import weight_limit_kg
from utils.serialization import editor_to_df, rows_to_df


def collect_weight_confirms(
    rows: Optional[List[Dict[str, Any]]],
    box_editor: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    if not rows:
        return []
    computed = with_computed_columns(rows_to_df(rows))
    pending = [w for w in check_gross_weight_consistency(computed) if w.get("requires_confirm")]
    if box_editor:
        editor_df = editor_to_df(box_editor)
        if not editor_df.empty:
            metrics = box_metrics(editor_df, dataframe_to_sku_rows(computed))
            limit = float(weight_limit_kg())
            for _, row in metrics.iterrows():
                kinds = int(row.get("SKU种类") or 0)
                gross = float(row.get("毛重(kg)") or 0)
                if kinds > 1 and gross > limit:
                    pending.append(
                        {
                            "row_index": int(row["箱号"]),
                            "sku": f"箱{int(row['箱号'])}",
                            "kind": "mixed_over_limit",
                            "requires_confirm": True,
                            "suggested_gross_kg": None,
                            "declared_kg": round(gross, 3),
                            "expected_kg": limit,
                            "message": (
                                f"混装箱 {int(row['箱号'])} 毛重 {gross:g} kg 超过上限 {limit:g} kg，导出前需要确认"
                            ),
                        }
                    )
    return pending


def raise_if_weight_unconfirmed(
    rows: Optional[List[Dict[str, Any]]],
    confirmed: bool,
    box_editor: Optional[List[Dict[str, Any]]] = None,
) -> None:
    if confirmed:
        return
    items = collect_weight_confirms(rows, box_editor)
    if not items:
        return
    raise HTTPException(
        status_code=409,
        detail={
            "code": "WEIGHT_CONFIRM_REQUIRED",
            "message": "毛重需要确认后才能导出",
            "items": items,
        },
    )


def parse_weight_rows(raw: Any) -> List[Dict[str, Any]]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []
    return []
