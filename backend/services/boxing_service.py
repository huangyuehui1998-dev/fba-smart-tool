"""Step 2 排箱编排:尾数池计算与装箱响应组装。"""
from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from fba_tool.fba_compliance import boxing_api_compliance
from utils.serialization import df_to_records


def compute_tail_pool(editor_df: pd.DataFrame, sku_rows) -> pd.DataFrame:
    shipped = editor_df.groupby("SKU简称")["数量"].sum().to_dict() if not editor_df.empty else {}
    rows = []
    for sku in sku_rows:
        total = int(sku.total_qty)
        packed = int(shipped.get(sku.sku, 0))
        remain = total - packed
        if remain > 0:
            rows.append({"SKU简称": sku.sku, "待排尾数": remain, "单个重量(kg)": sku.unit_weight_kg})
    # S8 D1：全部装完就是空池。以前这里退回 generate_box_plan 的“自动尾数”，界面会显示其实已装箱的件数，
    # 用户再分配就会超发。
    return pd.DataFrame(rows, columns=["SKU简称", "待排尾数", "单个重量(kg)"])


def boxing_response_payload(
    editor_df: pd.DataFrame,
    sku_rows,
    metrics_df: pd.DataFrame,
    *,
    tail_df: pd.DataFrame | None = None,
    transport_mode: str = "spd_partnered",
) -> Dict[str, Any]:
    enriched_metrics, compliance = boxing_api_compliance(
        editor_df, sku_rows, metrics_df, transport_mode=transport_mode
    )
    payload: Dict[str, Any] = {
        "box_editor": df_to_records(editor_df),
        "metrics": df_to_records(enriched_metrics),
        "has_overweight": bool(enriched_metrics["超重"].any()) if not enriched_metrics.empty else False,
        "fba_compliance": compliance,
        "has_fba_block": bool(compliance.get("blocked")),
    }
    if tail_df is not None:
        payload["tail_pool"] = df_to_records(tail_df)
    return payload
