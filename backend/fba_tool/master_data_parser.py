"""解析亚马逊费用预览报告 / 库存报告并提取主数据。

入库规范：尺寸统一 cm，重量统一 kg。
- 英寸 → cm：× inch_to_cm_factor（默认 2.54）
- 磅   → kg：× lb_to_kg_factor（1 lb = 0.45359237 kg，见 fba_tool.units）
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from fba_tool.table_loader import detect_table_format, load_raw_table
from fba_tool.volume_weight import detect_length_unit, detect_weight_unit, to_cm, to_kg

ReportKind = str  # "fee_preview" | "inventory"

# 模糊表头：按优先级匹配（归一化后 regex search）
SKU_PATTERNS = (r"\bsku\b", r"\bseller\s*sku\b", r"\bmsku\b")
ASIN_PATTERNS = (r"\basin\b", r"\basin\s*1\b")
FNSKU_PATTERNS = (r"\bfnsku\b", r"\bfulfillment\s*channel\s*sku\b", r"\bafn\s*sku\b")
LENGTH_PATTERNS = (r"\blongest\s*side\b", r"\blongest\b", r"\bitem\s*length\b", r"\blength\b", r"\blong\b")
WIDTH_PATTERNS = (r"\bmedian\s*side\b", r"\bmedian\b", r"\bitem\s*width\b", r"\bwidth\b", r"\bwide\b")
HEIGHT_PATTERNS = (r"\bshortest\s*side\b", r"\bshortest\b", r"\bitem\s*height\b", r"\bheight\b", r"\bhigh\b")
WEIGHT_PATTERNS = (
    r"\bitem\s*package\s*weight\b",
    r"\bpackage\s*weight\b",
    r"\bitem\s*weight\b",
    r"\bweight\b",
    r"\bmass\b",
)
DIM_UNIT_PATTERNS = (
    r"\bunit\s*of\s*dimension\b",
    r"\bdimension\s*unit\b",
    r"\blength\s*unit\b",
    r"\bitem\s*length\s*unit\b",
)
WT_UNIT_PATTERNS = (
    r"\bunit\s*of\s*weight\b",
    r"\bweight\s*unit\b",
    r"\bitem\s*weight\s*unit\b",
)


def parse_master_report(
    file_bytes: bytes,
    report_kind: ReportKind,
    filename: str = "",
) -> List[Dict[str, Any]]:
    df = _read_report_table(file_bytes, filename)
    if df.empty:
        return []
    if report_kind == "fee_preview":
        return _parse_fee_preview_df(df)
    if report_kind == "inventory":
        return _parse_inventory_df(df)
    raise ValueError(f"未知报告类型: {report_kind}")


def detect_report_kind(filename: str, file_bytes: bytes) -> ReportKind:
    name = (filename or "").lower()
    if "fee" in name and "preview" in name:
        return "fee_preview"
    if "inventory" in name or "listing" in name or "active" in name:
        return "inventory"
    df = _read_report_table(file_bytes, filename)
    cols = list(df.columns)
    if _pick_col_fuzzy(cols, LENGTH_PATTERNS) and _pick_col_fuzzy(cols, WEIGHT_PATTERNS):
        return "fee_preview"
    if _pick_col_fuzzy(cols, SKU_PATTERNS) and _pick_col_fuzzy(cols, ASIN_PATTERNS):
        return "inventory"
    return "fee_preview"


def _read_report_table(file_bytes: bytes, filename: str = "") -> pd.DataFrame:
    fmt = detect_table_format(file_bytes, filename)
    if fmt == "unknown" and not file_bytes:
        return pd.DataFrame()

    try:
        raw = load_raw_table(file_bytes, filename)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"报告文件读取失败：{exc}") from exc

    if raw.empty:
        return pd.DataFrame()

    headers = [_norm_col(c) for c in raw.iloc[0].tolist()]
    body = raw.iloc[1:].copy()
    body.columns = headers
    return body.reset_index(drop=True)


def _norm_col(name: Any) -> str:
    """表头归一化：小写、去标点、合并空白，便于模糊匹配。"""
    text = str(name or "").strip().lower()
    text = re.sub(r"[_\-\./\\()（）\[\]:;#]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _pick_col_fuzzy(cols: List[str], patterns: Tuple[str, ...]) -> Optional[str]:
    """按 regex 关键词在归一化表头中模糊匹配列名。"""
    for col in cols:
        norm = _norm_col(col)
        if not norm:
            continue
        for pattern in patterns:
            if re.search(pattern, norm):
                return col
    return None


def _parse_fee_preview_df(df: pd.DataFrame) -> List[Dict[str, Any]]:
    return _parse_report_rows(df, default_dim_unit="in", default_wt_unit="lb")


def _parse_inventory_df(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """库存报告：仅提取 SKU / ASIN / FNSKU，不解析尺寸（避免与单品/外箱混淆）。"""
    cols = list(df.columns)
    sku_col = _pick_col_fuzzy(cols, SKU_PATTERNS)
    asin_col = _pick_col_fuzzy(cols, ASIN_PATTERNS)
    fnsku_col = _pick_col_fuzzy(cols, FNSKU_PATTERNS)

    records: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        sku = _cell(row, sku_col)
        if not sku:
            continue
        records.append(
            {
                "sku": sku,
                "asin": _cell(row, asin_col) or None,
                "fnsku": _cell(row, fnsku_col) or None,
            }
        )
    return records


def _parse_report_rows(
    df: pd.DataFrame,
    *,
    default_dim_unit: str,
    default_wt_unit: str,
) -> List[Dict[str, Any]]:
    cols = list(df.columns)
    sku_col = _pick_col_fuzzy(cols, SKU_PATTERNS)
    asin_col = _pick_col_fuzzy(cols, ASIN_PATTERNS)
    fnsku_col = _pick_col_fuzzy(cols, FNSKU_PATTERNS)
    l_col = _pick_col_fuzzy(cols, LENGTH_PATTERNS)
    w_col = _pick_col_fuzzy(cols, WIDTH_PATTERNS)
    h_col = _pick_col_fuzzy(cols, HEIGHT_PATTERNS)
    wt_col = _pick_col_fuzzy(cols, WEIGHT_PATTERNS)
    dim_unit_col = _pick_col_fuzzy(cols, DIM_UNIT_PATTERNS)
    wt_unit_col = _pick_col_fuzzy(cols, WT_UNIT_PATTERNS)

    records: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        sku = _cell(row, sku_col)
        if not sku:
            continue
        l_raw = _to_float(_cell(row, l_col))
        w_raw = _to_float(_cell(row, w_col))
        h_raw = _to_float(_cell(row, h_col))
        weight_raw = _to_float(_cell(row, wt_col))

        dim_unit = _resolve_dim_unit(_cell(row, dim_unit_col), l_raw, w_raw, h_raw, default_dim_unit)
        wt_unit = _resolve_wt_unit(_cell(row, wt_unit_col), weight_raw, default_wt_unit)

        length, width, height = _sorted_dims_cm(l_raw, w_raw, h_raw, dim_unit)
        weight = to_kg(weight_raw, wt_unit) if weight_raw > 0 else None

        records.append(
            {
                "sku": sku,
                "asin": _cell(row, asin_col) or None,
                "fnsku": _cell(row, fnsku_col) or None,
                "unit_length": length,
                "unit_width": width,
                "unit_height": height,
                "unit_weight": weight,
            }
        )
    return records


def _resolve_dim_unit(unit_cell: str, l: float, w: float, h: float, default: str) -> str:
    """识别尺寸单位；无单位列时用数值启发式（>25 多为 cm）。"""
    if unit_cell:
        return detect_length_unit(unit_cell)
    positive = [v for v in (l, w, h) if v > 0]
    if positive and min(positive) >= 8 and max(positive) <= 120:
        return "cm"
    return default


def _resolve_wt_unit(unit_cell: str, weight: float, default: str) -> str:
    if unit_cell:
        return detect_weight_unit(unit_cell)
    if 0 < weight <= 3.0:
        return "kg"
    return default


def _sorted_dims_cm(l: float, w: float, h: float, unit: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if l <= 0 or w <= 0 or h <= 0:
        return None, None, None
    dims = sorted([to_cm(l, unit), to_cm(w, unit), to_cm(h, unit)], reverse=True)
    return round(dims[0], 1), round(dims[1], 1), round(dims[2], 1)


def _cell(row: pd.Series, col: Optional[str]) -> str:
    if not col:
        return ""
    val = row.get(col, "")
    if pd.isna(val):
        return ""
    return str(val).strip()


def _to_float(val: Any) -> float:
    if val is None or val == "":
        return 0.0
    try:
        return float(str(val).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0
