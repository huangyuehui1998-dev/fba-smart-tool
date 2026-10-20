"""发货装箱单 — 按「货件 + FNSKU」汇总，箱号合并显示。"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Tuple

import pandas as pd

from fba_tool.box_label_filename import (
    sort_pairs_by_box_label_pdf,
    ticket_prefix_for_pair,
    ticket_sort_num_for_pair,
)
from fba_tool.fnsku_resolve import (
    fnsku_map_from_csv_shipment,
    fnsku_map_from_pairs,
    fnsku_map_from_step1_rows,
    resolve_fnsku,
)
from fba_tool.user_config import throw_ratio as default_throw_ratio
from fba_tool.volume_weight import box_cbm

# DataFrame / 预览 / 导出共用的列键（顺序即列序）
SHIPPING_SHEET_COLUMNS = [
    "票数",
    "仓库代码",
    "FBA货件编号",
    "箱号",
    "亚马逊条码(FNSKU)",
    "中文品名",
    "总数量",
    "总毛重(KG)",
    "外箱长(CM)",
    "外箱宽(CM)",
    "外箱高(CM)",
    "单箱体积(CBM)",
]

# 列键 -> (中文表头, 英文副标题)
SHIPPING_SHEET_HEADERS: Dict[str, Tuple[str, str]] = {
    "票数": ("票数", "Ticket"),
    "仓库代码": ("仓库代码", "Warehouse"),
    "FBA货件编号": ("FBA 货件编号", "Shipment ID"),
    "箱号": ("箱号", "Carton No."),
    "亚马逊条码(FNSKU)": ("亚马逊条码", "FNSKU"),
    "中文品名": ("中文品名", "CN Name"),
    "总数量": ("总数量", "Total Qty"),
    "总毛重(KG)": ("总毛重(KG)", "Total G.W."),
    "外箱长(CM)": ("外箱长(CM)", "Length"),
    "外箱宽(CM)": ("外箱宽(CM)", "Width"),
    "外箱高(CM)": ("外箱高(CM)", "Height"),
    "单箱体积(CBM)": ("单箱体积(CBM)", "Volume"),
}

# 顶部浅色字段带 — 列键与 Step 1 录入字段一致
SHIPPING_SHEET_LEGEND_COLUMNS = [
    "SKU简称",
    "发货总数",
    "单箱装量",
    "箱长(cm)",
    "箱宽(cm)",
    "箱高(cm)",
]

# 表头展示（带 * 必填标记）
SHIPPING_SHEET_LEGEND = [f"{c}*" for c in SHIPPING_SHEET_LEGEND_COLUMNS]

# Step 1 浅色字段带列位：SKU 占首 3 列，其余字段相对原布局右移 2 列
SHIPPING_SHEET_LEGEND_SKU_SPAN = 3
SHIPPING_SHEET_LEGEND_COLUMN: Dict[str, int] = {
    "SKU简称": 1,
    "发货总数": 4,
    "单箱装量": 5,
    "箱长(cm)": 6,
    "箱宽(cm)": 7,
    "箱高(cm)": 8,
}


def _fnsku_for_item(
    sku: str,
    csv_fnsku: str,
    step1_map: Dict[str, str],
    catalog,
) -> str:
    return resolve_fnsku(
        sku,
        csv_fnsku=csv_fnsku,
        step1_fnsku=step1_map.get(sku, ""),
        catalog=catalog,
    )


def _cn_name(sku: str, catalog) -> str:
    from fba_tool.master_db import get_product_by_sku, lookup_customs_name, lookup_model_name

    name = lookup_model_name(sku) or lookup_customs_name(sku)
    if name:
        return name
    rec = get_product_by_sku(sku)
    if rec and rec.get("english_name"):
        return str(rec["english_name"]).strip()
    return str(sku or "").strip()


def _spec_by_box(specs: pd.DataFrame) -> Dict[int, pd.Series]:
    out: Dict[int, pd.Series] = {}
    if specs is None or specs.empty or "箱号" not in specs.columns:
        return out
    for _, row in specs.iterrows():
        try:
            out[int(row["箱号"])] = row
        except (TypeError, ValueError):
            continue
    return out


def _items_by_box(items: pd.DataFrame) -> Dict[int, List[Tuple[str, int, str]]]:
    out: Dict[int, List[Tuple[str, int, str]]] = defaultdict(list)
    if items is None or items.empty or "箱号" not in items.columns:
        return out
    for _, row in items.iterrows():
        try:
            box = int(row["箱号"])
        except (TypeError, ValueError):
            continue
        sku = str(row.get("SKU", "")).strip()
        qty = int(float(row.get("数量", 0) or 0))
        fnsku = str(row.get("FNSKU", "") or "").strip()
        if sku and qty > 0:
            out[box].append((sku, qty, fnsku))
    return out


def _format_box_nums(seqs: List[int]) -> str:
    return ",".join(str(s) for s in sorted(seqs))


def _dims_consistent(dims: List[Tuple[float, float, float]]) -> Tuple[float, float, float] | None:
    if not dims:
        return None
    first = dims[0]
    if all(d == first for d in dims):
        return first
    return None


def build_shipping_sheet_df(
    pairs: List[Any],
    *,
    throw_ratio: float | None = None,
    step1_rows: List[Dict[str, Any]] | None = None,
) -> pd.DataFrame:
    _ = float(throw_ratio if throw_ratio is not None else default_throw_ratio())
    catalog = None
    step1_map = fnsku_map_from_step1_rows(step1_rows)

    ordered_pairs = sort_pairs_by_box_label_pdf(pairs)
    ticket_by_shipment: Dict[str, str] = {}
    ticket_sort_by_shipment: Dict[str, int] = {}
    for i, pair in enumerate(ordered_pairs, start=1):
        sid = str(pair.shipment_id or "").strip()
        if sid:
            ticket_by_shipment[sid] = ticket_prefix_for_pair(pair, i)
            ticket_sort_by_shipment[sid] = ticket_sort_num_for_pair(pair, i)

    # (货件编号, FNSKU) -> 汇总
    groups: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for pair in pairs:
        shipment_id = str(pair.shipment_id or "").strip()
        warehouse = str(pair.warehouse_code or "").strip()
        ticket = ticket_by_shipment.get(shipment_id, "")
        ticket_sort = ticket_sort_by_shipment.get(shipment_id, 9999)
        spec_map = _spec_by_box(pair.csv.box_specs)
        item_map = _items_by_box(pair.csv.box_items)
        csv_fnsku_map = fnsku_map_from_csv_shipment(pair.csv)
        boxes = sorted(set(spec_map.keys()) | set(item_map.keys()))

        for seq, box_no in enumerate(boxes, start=1):
            spec = spec_map.get(box_no)
            sku_list = item_map.get(box_no, [])
            if not sku_list:
                continue

            if spec is not None:
                length = round(float(spec.get("长(cm)", 0) or 0), 1)
                width = round(float(spec.get("宽(cm)", 0) or 0), 1)
                height = round(float(spec.get("高(cm)", 0) or 0), 1)
                gross = round(float(spec.get("实重(kg)", 0) or 0), 2)
                cbm = round(box_cbm(length, width, height), 3)
                dims = (length, width, height)
            else:
                gross = 0.0
                cbm = 0.0
                dims = (0.0, 0.0, 0.0)

            for sku, qty, row_fnsku in sku_list:
                csv_fn = row_fnsku or csv_fnsku_map.get(sku, "")
                fnsku = _fnsku_for_item(sku, csv_fn, step1_map, catalog)
                group_id = fnsku if fnsku else sku
                key = (shipment_id, group_id)
                if key not in groups:
                    groups[key] = {
                        "票数": ticket,
                        "ticket_sort": ticket_sort,
                        "仓库代码": warehouse,
                        "FBA货件编号": shipment_id,
                        "亚马逊条码(FNSKU)": fnsku,
                        "中文品名": _cn_name(sku, catalog),
                        "box_seqs": [],
                        "qty": 0,
                        "gross": 0.0,
                        "cbm": 0.0,
                        "dims": [],
                        "sort_key": seq,
                    }
                g = groups[key]
                g["qty"] += qty
                if seq not in g["box_seqs"]:
                    g["box_seqs"].append(seq)
                    g["gross"] += gross
                    g["cbm"] += cbm
                    g["dims"].append(dims)
                g["sort_key"] = min(g["sort_key"], seq)

    rows: List[Dict[str, Any]] = []
    for key in sorted(
        groups.keys(),
        key=lambda k: (
            groups[k].get("ticket_sort", 9999),
            k[0],
            groups[k]["sort_key"],
            k[1],
        ),
    ):
        g = groups[key]
        dims = _dims_consistent(g["dims"])
        rows.append(
            {
                "票数": g["票数"],
                "仓库代码": g["仓库代码"],
                "FBA货件编号": g["FBA货件编号"],
                "箱号": _format_box_nums(g["box_seqs"]),
                "亚马逊条码(FNSKU)": g["亚马逊条码(FNSKU)"],
                "中文品名": g["中文品名"],
                "总数量": g["qty"],
                "总毛重(KG)": round(g["gross"], 2),
                "外箱长(CM)": dims[0] if dims else "",
                "外箱宽(CM)": dims[1] if dims else "",
                "外箱高(CM)": dims[2] if dims else "",
                "单箱体积(CBM)": round(g["cbm"], 3),
            }
        )

    if not rows:
        return pd.DataFrame(columns=SHIPPING_SHEET_COLUMNS)
    return pd.DataFrame(rows, columns=SHIPPING_SHEET_COLUMNS)


def _skus_in_pairs(pairs: List[Any], step1_map: Dict[str, str], catalog) -> Tuple[set[str], set[str]]:
    skus: set[str] = set()
    fnskus: set[str] = set()
    for pair in pairs:
        item_map = _items_by_box(pair.csv.box_items)
        csv_fnsku_map = fnsku_map_from_csv_shipment(pair.csv)
        for sku_list in item_map.values():
            for sku, _, row_fnsku in sku_list:
                key = str(sku or "").strip()
                if not key:
                    continue
                skus.add(key)
                fn = _fnsku_for_item(key, row_fnsku or csv_fnsku_map.get(key, ""), step1_map, catalog)
                if fn:
                    fnskus.add(fn)
    return skus, fnskus


def build_shipping_sheet_legend(
    step1_rows: List[Dict[str, Any]] | None,
    pairs: List[Any] | None = None,
) -> List[Dict[str, Any]]:
    """从 Step 1 录入生成发货表顶部浅色字段带数据。"""
    if not step1_rows:
        return []

    catalog = None
    step1_map = fnsku_map_from_step1_rows(step1_rows)
    skus_in_shipment: set[str] = set()
    fnskus_in_shipment: set[str] = set()
    if pairs:
        skus_in_shipment, fnskus_in_shipment = _skus_in_pairs(pairs, step1_map, catalog)
        fnskus_in_shipment |= set(fnsku_map_from_pairs(pairs).values())

    legend_rows: List[Dict[str, Any]] = []
    for row in step1_rows:
        sku = str(row.get("SKU简称") or "").strip()
        if not sku:
            continue
        fnsku = str(row.get("FNSKU") or "").strip()
        if skus_in_shipment and sku not in skus_in_shipment and fnsku not in fnskus_in_shipment:
            continue
        legend_rows.append(
            {
                "SKU简称": sku,
                "发货总数": row.get("发货总数", ""),
                "单箱装量": row.get("单箱装量", ""),
                "箱长(cm)": row.get("箱长(cm)", ""),
                "箱宽(cm)": row.get("箱宽(cm)", ""),
                "箱高(cm)": row.get("箱高(cm)", ""),
            }
        )
    return legend_rows
