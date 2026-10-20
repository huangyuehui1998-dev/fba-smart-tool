"""Step 4 货代报价表：Extract → Normalize → Group by SKU → Output"""



from __future__ import annotations



from typing import Any, Dict, List, Optional



import pandas as pd



from fba_tool.user_config import throw_ratio as default_throw_ratio
from fba_tool.volume_weight import box_cbm, to_cm, to_kg, volume_weight_kg



GROUP_KEY = ["仓库代码", "长(cm)", "宽(cm)", "高(cm)", "实重(kg)"]

SKU_GROUP_KEY = ["仓库代码", "SKU"]



FORWARDER_COLUMNS = [
    "仓库代码",
    "SKU",
    "箱序号",
    "箱数",
    "箱子长(cm)",
    "箱子宽(cm)",
    "箱子高(cm)",
    "单箱体积重(kg)",
    "总体积重(kg)",
    "单箱实重(kg)",
    "总实重(kg)",
    "单箱装量",
    "发货总数",
    "单件实重(kg)",
]



SUBTOTAL_FLAG = "_subtotal"

SUBTOTAL_CBM_FLAG = "_subtotal_cbm"

DETAIL_CBM_FLAG = "_detail_cbm"



DIM_FIELDS = ("箱子长(cm)", "箱子宽(cm)", "箱子高(cm)")





def is_forwarder_subtotal_row(row: pd.Series | dict) -> bool:

    return _is_subtotal_row(row)





def _is_subtotal_row(row: pd.Series | dict) -> bool:

    if isinstance(row, pd.Series):

        if SUBTOTAL_FLAG in row.index and bool(row.get(SUBTOTAL_FLAG)):

            return True

        wh = str(row.get("仓库代码", ""))

    else:

        if row.get(SUBTOTAL_FLAG):

            return True

        wh = str(row.get("仓库代码", ""))

    return wh.endswith(" 小计")





def _strip_subtotal_rows(df: pd.DataFrame) -> pd.DataFrame:

    if df.empty:

        return df

    work = df.copy()

    if SUBTOTAL_FLAG in work.columns:

        work = work[~work[SUBTOTAL_FLAG].fillna(False).astype(bool)]

    if "仓库代码" in work.columns:

        work = work[~work["仓库代码"].astype(str).str.endswith(" 小计")]

    return work.reset_index(drop=True)





def forwarder_detail_row_cbm(row: pd.Series | dict) -> float:

    """明细行方数 = 分摊 CBM（优先）或 单箱 CBM × 箱数"""

    if isinstance(row, pd.Series):

        detail_cbm = row.get(DETAIL_CBM_FLAG)

    else:

        detail_cbm = row.get(DETAIL_CBM_FLAG)

    if detail_cbm not in (None, ""):

        try:

            return round(float(detail_cbm), 3)

        except (TypeError, ValueError):

            pass



    l = float(row.get("箱子长(cm)", 0) or 0)

    w = float(row.get("箱子宽(cm)", 0) or 0)

    h = float(row.get("箱子高(cm)", 0) or 0)

    boxes = int(row.get("箱数", 0) or 0)

    if l <= 0 or w <= 0 or h <= 0 or boxes <= 0:

        return 0.0

    return round(box_cbm(l, w, h) * boxes, 3)





def compute_forwarder_total_cbm(forwarder_df: pd.DataFrame) -> float:

    detail = _strip_subtotal_rows(forwarder_df)

    if detail.empty:

        return 0.0

    return round(sum(forwarder_detail_row_cbm(row) for _, row in detail.iterrows()), 3)





def format_subtotal_cbm_label(cbm: float) -> str:

    return f"方数: {cbm:.3f} CBM"





def _format_box_seq(box_nos: List[int]) -> str:
    nums = sorted({int(b) for b in box_nos if int(b) > 0})
    return ",".join(str(n) for n in nums)


def append_warehouse_subtotals(forwarder_df: pd.DataFrame) -> pd.DataFrame:
    """在每个仓库明细块末尾插入分仓小计行（幂等）。"""
    if forwarder_df.empty:
        return forwarder_df

    detail = _strip_subtotal_rows(forwarder_df)
    if detail.empty or "仓库代码" not in detail.columns:
        return forwarder_df

    wh_order: List[str] = []
    for wh in detail["仓库代码"].astype(str).tolist():
        if wh not in wh_order:
            wh_order.append(wh)

    rows: List[Dict] = []
    for wh in wh_order:
        block = detail[detail["仓库代码"].astype(str) == wh]
        for _, row in block.iterrows():
            rec = {col: row.get(col, "") for col in FORWARDER_COLUMNS if col in detail.columns}
            rec[SUBTOTAL_FLAG] = False
            if DETAIL_CBM_FLAG in detail.columns:
                rec[DETAIL_CBM_FLAG] = row.get(DETAIL_CBM_FLAG)
            rows.append(rec)

        box_sum = int(block["箱数"].sum()) if "箱数" in block.columns else 0
        qty_sum = int(pd.to_numeric(block["发货总数"], errors="coerce").sum()) if "发货总数" in block.columns else 0
        gross_sum = round(float(block["总实重(kg)"].sum()), 2) if "总实重(kg)" in block.columns else 0.0
        vol_sum = round(float(block["总体积重(kg)"].sum()), 3) if "总体积重(kg)" in block.columns else 0.0
        cbm_sum = round(sum(forwarder_detail_row_cbm(row) for _, row in block.iterrows()), 3)

        subtotal: Dict = {col: "" for col in FORWARDER_COLUMNS}
        subtotal.update(
            {
                "仓库代码": f"{wh} 小计",
                "发货总数": qty_sum if qty_sum > 0 else "",
                "箱数": box_sum,
                "箱子长(cm)": format_subtotal_cbm_label(cbm_sum),
                "箱子宽(cm)": "",
                "箱子高(cm)": "",
                "总实重(kg)": gross_sum,
                "总体积重(kg)": vol_sum,
                SUBTOTAL_FLAG: True,
                SUBTOTAL_CBM_FLAG: cbm_sum,
            }
        )
        rows.append(subtotal)

    out_cols = [c for c in FORWARDER_COLUMNS if c in detail.columns]
    for extra in (SUBTOTAL_FLAG, SUBTOTAL_CBM_FLAG, DETAIL_CBM_FLAG):
        if extra not in out_cols and any(extra in r for r in rows):
            out_cols.append(extra)
    return pd.DataFrame(rows, columns=out_cols)


def build_forwarder_df(

    box_specs_df: pd.DataFrame,

    box_items_df: Optional[pd.DataFrame] = None,

    throw_ratio: float | None = None,

) -> pd.DataFrame:

    """按 SKU 合并货代明细；箱规/重量按箱内 SKU 件数比例分摊，避免混装重复计费。"""

    ratio = float(throw_ratio if throw_ratio is not None else default_throw_ratio())

    if box_specs_df.empty:

        return pd.DataFrame(columns=FORWARDER_COLUMNS)



    if box_items_df is not None and not box_items_df.empty:

        return _build_forwarder_by_sku(box_specs_df, box_items_df, ratio)



    return _build_forwarder_by_specs(box_specs_df, ratio)





def _build_forwarder_by_sku(

    box_specs_df: pd.DataFrame,

    box_items_df: pd.DataFrame,

    ratio: float,

) -> pd.DataFrame:

    specs = _normalize_specs_df(box_specs_df)

    if specs.empty:

        return pd.DataFrame(columns=FORWARDER_COLUMNS)



    items = box_items_df.copy()

    for col in ("仓库代码", "箱号", "SKU", "数量"):

        if col not in items.columns:

            return _build_forwarder_by_specs(box_specs_df, ratio)



    items["箱号"] = items["箱号"].astype(int)

    items["SKU"] = items["SKU"].astype(str).str.strip()

    items["数量"] = items["数量"].apply(lambda v: max(0, int(float(v or 0))))

    items = items[(items["SKU"] != "") & (items["数量"] > 0)]



    spec_cols = ["仓库代码", "箱号", "长(cm)", "宽(cm)", "高(cm)", "实重(kg)"]
    merged = items.merge(specs[spec_cols], on=["仓库代码", "箱号"], how="inner")

    if merged.empty:

        return pd.DataFrame(columns=FORWARDER_COLUMNS)



    box_totals = merged.groupby(["仓库代码", "箱号"], as_index=False)["数量"].sum().rename(

        columns={"数量": "_box_total_qty"}

    )

    merged = merged.merge(box_totals, on=["仓库代码", "箱号"], how="left")

    merged["_share"] = merged["数量"] / merged["_box_total_qty"].replace(0, 1)

    merged["_alloc_kg"] = merged["实重(kg)"] * merged["_share"]

    merged["_alloc_vol"] = merged.apply(

        lambda r: volume_weight_kg(r["长(cm)"], r["宽(cm)"], r["高(cm)"], throw_ratio=ratio)

        * float(r["_share"]),

        axis=1,

    )

    merged["_alloc_cbm"] = merged.apply(

        lambda r: box_cbm(r["长(cm)"], r["宽(cm)"], r["高(cm)"]) * float(r["_share"]),

        axis=1,

    )

    merged["_unit_kg"] = merged["_alloc_kg"] / merged["数量"]



    records: List[Dict] = []

    for (wh, sku), group in merged.groupby(SKU_GROUP_KEY, sort=True):

        qty_sum = int(group["数量"].sum())

        if qty_sum <= 0:

            continue



        box_nos = group["箱号"].astype(int).tolist()

        gross = round(float(group["_alloc_kg"].sum()), 2)

        vol_total = round(float(group["_alloc_vol"].sum()), 3)

        detail_cbm = round(float(group["_alloc_cbm"].sum()), 3)



        weights = group["数量"].astype(float)

        avg_l = round(float((group["长(cm)"] * weights).sum() / weights.sum()), 1)

        avg_w = round(float((group["宽(cm)"] * weights).sum() / weights.sum()), 1)

        avg_h = round(float((group["高(cm)"] * weights).sum() / weights.sum()), 1)

        single_vol = volume_weight_kg(avg_l, avg_w, avg_h, throw_ratio=ratio)

        unit_kg = round(float(group["_alloc_kg"].sum() / qty_sum), 3)



        box_count = len(set(box_nos))
        single_box_gross = round(float(group["_alloc_kg"].sum() / box_count), 2)
        qty_per_box = int(qty_sum / box_count) if qty_sum % box_count == 0 else round(qty_sum / box_count, 2)

        records.append(

            {

                "仓库代码": wh,

                "SKU": sku,

                "箱序号": _format_box_seq(box_nos),

                "发货总数": qty_sum,
                "单箱装量": qty_per_box,
                "单箱实重(kg)": single_box_gross,
                "单件实重(kg)": unit_kg,

                "箱数": box_count,

                "箱子长(cm)": avg_l,

                "箱子宽(cm)": avg_w,

                "箱子高(cm)": avg_h,

                "总实重(kg)": gross,

                "单箱体积重(kg)": single_vol,

                "总体积重(kg)": vol_total,

                DETAIL_CBM_FLAG: detail_cbm,

            }

        )



    frame = pd.DataFrame(records, columns=[*FORWARDER_COLUMNS, DETAIL_CBM_FLAG])

    return append_warehouse_subtotals(frame)





def _build_forwarder_by_specs(box_specs_df: pd.DataFrame, ratio: float) -> pd.DataFrame:

    """无装箱 SKU 明细时的兜底：仍按箱规尺寸分组。"""

    specs = _normalize_specs_df(box_specs_df)

    if specs.empty:

        return pd.DataFrame(columns=FORWARDER_COLUMNS)



    grouped = (

        specs.groupby(GROUP_KEY, dropna=False)

        .size()

        .reset_index(name="箱数")

        .sort_values(GROUP_KEY)

        .reset_index(drop=True)

    )



    records: List[Dict] = []

    for _, row in grouped.iterrows():

        box_count = int(row["箱数"])

        single_kg = float(row["实重(kg)"])

        l, w, h = float(row["长(cm)"]), float(row["宽(cm)"]), float(row["高(cm)"])

        single_vol = volume_weight_kg(l, w, h, throw_ratio=ratio)

        records.append(

            {

                "仓库代码": row["仓库代码"],

                "SKU": "",

                "箱序号": "",

                "发货总数": "",
                "单箱装量": "",
                "单箱实重(kg)": single_kg,
                "单件实重(kg)": "",
                "箱数": box_count,

                "箱子长(cm)": l,

                "箱子宽(cm)": w,
                "箱子高(cm)": h,
                "总实重(kg)": round(single_kg * box_count, 2),
                "单箱体积重(kg)": single_vol,
                "总体积重(kg)": round(single_vol * box_count, 3),

            }

        )

    return append_warehouse_subtotals(pd.DataFrame(records, columns=FORWARDER_COLUMNS))


def sort_forwarder_by_warehouse_ticket(forwarder_df: pd.DataFrame, pairs: List[Any]) -> pd.DataFrame:
    """按仓库对应票序排序货代表明细，再重建分仓小计。"""
    if forwarder_df.empty or not pairs:
        return forwarder_df
    from fba_tool.box_label_filename import warehouse_ticket_rank

    detail = _strip_subtotal_rows(forwarder_df)
    if detail.empty:
        return forwarder_df

    rank = warehouse_ticket_rank(pairs)
    extra_cols = [c for c in forwarder_df.columns if c not in FORWARDER_COLUMNS]
    work = detail.copy()
    work["_ticket_rank"] = work["仓库代码"].astype(str).map(lambda w: rank.get(w, 9999))
    sort_cols = ["_ticket_rank", "仓库代码"]
    if "SKU" in work.columns:
        sort_cols.append("SKU")
    work = work.sort_values(sort_cols, kind="stable").drop(columns=["_ticket_rank"])
    for col in extra_cols:
        if col not in work.columns and col in forwarder_df.columns:
            work[col] = forwarder_df[col]
    return append_warehouse_subtotals(work)





def _normalize_specs_df(df: pd.DataFrame) -> pd.DataFrame:

    """对已提取的箱规表再次抹平精度，确保分组 Key 一致。"""

    if df.empty:

        return df

    out = df.copy()

    out["箱号"] = out["箱号"].astype(int) if "箱号" in out.columns else out.index + 1

    for col in ("长(cm)", "宽(cm)", "高(cm)"):

        if col in out.columns:

            out[col] = out[col].apply(lambda v: to_cm(float(v or 0), "cm"))

    if "实重(kg)" in out.columns:

        out["实重(kg)"] = out["实重(kg)"].apply(lambda v: to_kg(float(v or 0), "kg"))

    out = out[(out["长(cm)"] > 0) & (out["宽(cm)"] > 0) & (out["高(cm)"] > 0) & (out["实重(kg)"] > 0)]

    return out.reset_index(drop=True)


