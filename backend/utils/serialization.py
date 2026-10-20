"""DataFrame ↔ JSON 序列化与上传读取等通用数据工具。"""
from __future__ import annotations

import math
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from fastapi import UploadFile

from fba_tool.data_processing import INPUT_COLUMNS, empty_input_df
from fba_tool.master_data_apply import apply_master_to_input_rows


def rows_to_df(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return empty_input_df()
    df = pd.DataFrame(rows)
    for col in INPUT_COLUMNS:
        if col not in df.columns:
            df[col] = "" if col == "FNSKU" else (None if col == "单箱毛重(kg)" else 0)
    return df[INPUT_COLUMNS]


def editor_to_df(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    cols = ["箱号", "来源", "SKU简称", "数量"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = 0 if c in {"箱号", "数量"} else ""
    return df[cols]


def sanitize_json_value(value: Any) -> Any:
    """将 NaN / Inf 及 numpy 标量转为 JSON 可序列化类型。"""
    if value is None:
        return None
    if isinstance(value, (np.floating, float)):
        fv = float(value)
        if math.isnan(fv) or math.isinf(fv):
            return None
        return fv
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if pd.isna(value):
        return None
    return value


def rows_to_df_with_master(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    merged, _ = apply_master_to_input_rows(rows)
    return rows_to_df(merged)


def df_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    records = df.to_dict(orient="records")
    return [{k: sanitize_json_value(v) for k, v in row.items()} for row in records]


def validation_errors_payload(errors: list) -> List[Dict[str, Any]]:
    return [{"row_index": int(r), "row_number": int(r) + 1, "field": c} for r, c in errors]


def read_uploads(files: List[UploadFile]) -> List[tuple[str, bytes]]:
    payload: List[tuple[str, bytes]] = []
    for f in files:
        payload.append((f.filename or "upload", f.file.read()))
    return payload
