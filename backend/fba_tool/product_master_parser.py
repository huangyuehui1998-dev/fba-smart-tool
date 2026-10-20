"""业务《产品信息总表》解析：正则模糊表头 + SKU 行定位（忽略商标等非主表 Sheet）。"""

from __future__ import annotations



import json

import re

from typing import Any, Dict, List, Optional, Tuple



import pandas as pd



from fba_tool.table_loader import detect_table_format, iter_excel_sheet_frames, load_raw_table



# 清洗后表头 → 标准字段（regex search，忽略大小写）

# chinese_name / model_name 由专用函数按列名优先级匹配

PRODUCT_MASTER_REGEX_MAP: Dict[str, str] = {

    "sku": r"SKU",

    "english_name": r"产品名称|物品英文名|英文品名",

    "qty_per_box": r"单箱内数量|每箱数量|箱内数量",

    "hs_code": r"美国海关编码|海关编码|HS\s*CODE",

    "material": r"材质",

    "purpose": r"用途",

    "brand": r"品牌",

    "declared_value": r"售价\(客户到手价格\)|产品成本|申报单价",

    "fnsku": r"美国站[-_]?FNSKU|FNSKU",

    "asin": r"ASIN",

}



CHINESE_NAME_PRIORITY = (

    re.compile(r"物品中文名"),

    re.compile(r"商品报关名称"),

    re.compile(r"报关名称"),

)



MODEL_NAME_PRIORITY = (

    re.compile(r"中文名称"),

)



SKIP_SHEET_PATTERN = re.compile(r"商标|trademark|brand\s*mark", re.I)

PRODUCT_INFO_SHEET_PATTERN = re.compile(r"产品信息", re.I)

INVALID_SKU_ROW = re.compile(

    r"填写|说明|备注|即将淘汰|运营部分|表格|填充|颜色|标注|示例|禁止|请勿",

    re.I,

)

SKU_HEADER_PATTERN = re.compile(r"SKU", re.I)



_HEADER_SCAN_ROWS = 50





def _compact_header(text: Any) -> str:

    """去掉换行/空白，便于正则匹配脏表头。"""

    return re.sub(r"[\n\r\s]+", "", str(text or ""))





def _unique_headers(headers: List[str]) -> List[str]:

    """重复表头追加后缀，避免 df[列名] 返回多列 DataFrame。"""

    seen: Dict[str, int] = {}

    out: List[str] = []

    for h in headers:

        base = h or ""

        n = seen.get(base, 0) + 1

        seen[base] = n

        out.append(base if n == 1 else f"{base}__{n}")

    return out





def _pick_customs_name_column(columns: List[str]) -> Optional[str]:

    """商品报关名称 → chinese_name（发票/报关）。"""

    for pat in CHINESE_NAME_PRIORITY:

        for col in columns:

            if col and pat.search(col):

                return col

    return None





def _pick_model_name_column(columns: List[str]) -> Optional[str]:

    """中文名称(型号) → model_name（工人实操单、发货表）。"""

    for pat in MODEL_NAME_PRIORITY:

        for col in columns:

            if col and pat.search(col):

                return col

    return None





def _read_raw_table(file_bytes: bytes, filename: str = "") -> pd.DataFrame:

    fmt = detect_table_format(file_bytes, filename)

    if fmt in ("xlsx", "xlsm", "xls", "xlsb"):

        return _read_excel_raw(file_bytes, filename)

    return load_raw_table(file_bytes, filename)





def _read_excel_raw(file_bytes: bytes, filename: str = "") -> pd.DataFrame:

    """优先选含「产品信息」且含 SKU 表头的 Sheet（兼容多 Sheet 总表）。"""

    fallback: Optional[pd.DataFrame] = None

    best: Optional[Tuple[int, pd.DataFrame]] = None



    for sheet, df in iter_excel_sheet_frames(file_bytes, filename):

        if SKIP_SHEET_PATTERN.search(sheet):

            continue

        if df.empty:

            continue

        if fallback is None:

            fallback = df

        if _find_header_row(df) is None:

            continue

        score = len(df)

        if PRODUCT_INFO_SHEET_PATTERN.search(sheet):

            score += 10_000

        if best is None or score > best[0]:

            best = (score, df)



    if best is not None:

        return best[1]

    return fallback if fallback is not None else pd.DataFrame()





def _find_header_row(df: pd.DataFrame, scan_rows: int = _HEADER_SCAN_ROWS) -> Optional[int]:

    limit = min(scan_rows, len(df))

    for i in range(limit):

        row = df.iloc[i].astype(str)

        if row.str.contains(SKU_HEADER_PATTERN, na=False).any():

            return i

    return None





def _frame_from_header_row(df: pd.DataFrame) -> pd.DataFrame:

    header_idx = _find_header_row(df)

    if header_idx is None:

        header_idx = 0

    headers = _unique_headers([_compact_header(c) for c in df.iloc[header_idx].tolist()])

    body = df.iloc[header_idx + 1 :].copy()

    body.columns = headers

    return body.reset_index(drop=True)





def _match_columns(columns: List[str]) -> Tuple[Dict[str, str], List[str]]:

    """返回 {标准字段: 原始列名} 与未映射列名列表。"""

    mapped: Dict[str, str] = {}

    used: set[str] = set()



    cn_col = _pick_customs_name_column(columns)

    if cn_col:

        mapped["chinese_name"] = cn_col

        used.add(cn_col)



    model_col = _pick_model_name_column(columns)

    if model_col:

        mapped["model_name"] = model_col

        used.add(model_col)



    for target, pattern in PRODUCT_MASTER_REGEX_MAP.items():

        for col in columns:

            if col in used:

                continue

            if re.search(pattern, col, re.IGNORECASE):

                mapped[target] = col

                used.add(col)

                break



    unmapped = [c for c in columns if c and c not in used]

    return mapped, unmapped





def _normalize_sku(val: Any) -> str:

    text = str(val or "").strip()

    if not text or text.lower() in ("nan", "none"):

        return ""

    if re.fullmatch(r"\d+\.?\d*[eE][+\-]?\d+", text):

        try:

            text = str(int(float(text)))

        except (ValueError, OverflowError):

            pass

    return text





def parse_business_product_master(

    file_bytes: bytes,

    filename: str = "",

) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:

    """解析业务产品信息总表 → 标准记录列表 + 列映射报告。"""

    raw = _read_raw_table(file_bytes, filename)

    if raw.empty:

        return [], {}



    df = _frame_from_header_row(raw)

    df.columns = [_compact_header(c) for c in df.columns]

    col_map, unmapped_cols = _match_columns(list(df.columns))



    if "sku" not in col_map:

        raise ValueError("未在表头中找到 SKU 列，请确认上传的是产品信息主表")



    mapped_data: Dict[str, pd.Series] = {}

    for field, src_col in col_map.items():

        mapped_data[field] = df[src_col].astype(str).str.strip()



    clean = pd.DataFrame(mapped_data)

    clean["sku"] = clean["sku"].map(_normalize_sku)

    clean = clean[clean["sku"].astype(bool)]

    clean = clean[~clean["sku"].str.contains(INVALID_SKU_ROW, na=False)]



    if "declared_value" in clean.columns:

        clean["declared_value"] = pd.to_numeric(clean["declared_value"], errors="coerce")



    if unmapped_cols:



        def _extra_for_index(idx: Any) -> str:

            row = df.loc[idx]

            bag: Dict[str, Any] = {}

            for col in unmapped_cols:

                val = str(row.get(col, "") or "").strip()

                if val and val.lower() != "nan":

                    bag[col] = val

            return json.dumps(bag, ensure_ascii=False) if bag else ""



        clean["extra_data"] = [_extra_for_index(idx) for idx in clean.index]

    else:

        clean["extra_data"] = ""



    records: List[Dict[str, Any]] = []

    for _, row in clean.iterrows():

        rec: Dict[str, Any] = {"sku": row["sku"]}

        for field in col_map:

            if field == "sku":

                continue

            val = row.get(field)

            if val in (None, "", "nan"):

                continue

            if field == "declared_value":

                rec[field] = _opt_float(val)

            else:

                rec[field] = str(val).strip()

        extra = row.get("extra_data")

        if extra:

            rec["extra_data"] = extra

        records.append(rec)



    return records, {k: v for k, v in col_map.items()}





def _opt_float(val: Any) -> Optional[float]:

    if val in (None, ""):

        return None

    try:

        n = float(val)

        return n if n > 0 else None

    except (TypeError, ValueError):

        return None

