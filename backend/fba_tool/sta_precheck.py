"""STA 预检：必填项为空，或预处理列不在官方下拉取值里，就记一条高亮。"""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

from openpyxl import load_workbook

REQUIRED_COLUMNS = (
    "SKU",
    "商品名称",
    "ASIN",
    "FNSKU",
    "状况",
    "预处理类型",
    "商品贴标方是谁？",
    "预计数量",
)

DROPDOWN_COLUMNS = (
    "预处理类型",
    "商品预处理方是谁？",
    "商品贴标方是谁？",
    "状况",
)


def _config_path() -> Path:
    override = Path("app_data/config/sta_dropdowns.json")
    if override.is_file():
        return override
    here = Path(__file__).resolve().parents[1] / "config" / "sta_dropdowns.default.json"
    return here


def load_sta_dropdowns() -> Dict[str, Any]:
    path = _config_path()
    return json.loads(path.read_text(encoding="utf-8"))


def _norm_header(value: Any) -> str:
    return str(value or "").strip()


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def precheck_sta_rows(rows: List[List[Any]], dropdowns: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """rows 是二维表。找到含「预处理类型」的表头行，逐行检查。"""
    catalog = dropdowns if dropdowns is not None else load_sta_dropdowns()
    allowed = {name: set(values) for name, values in (catalog.get("columns") or {}).items()}
    header_idx = None
    for i, row in enumerate(rows):
        headers = [_norm_header(cell) for cell in row]
        if "预处理类型" in headers and "SKU" in headers:
            header_idx = i
            break
    if header_idx is None:
        return [{"row": 1, "column": "表头", "message": "没有找到 STA 表头"}]

    headers = [_norm_header(cell) for cell in rows[header_idx]]
    index = {name: pos for pos, name in enumerate(headers) if name}
    highlights: List[Dict[str, Any]] = []
    for offset, row in enumerate(rows[header_idx + 1 :], start=1):
        if not any(_cell_text(cell) for cell in row):
            continue
        excel_row = header_idx + 1 + offset
        sku = _cell_text(row[index["SKU"]]) if "SKU" in index and index["SKU"] < len(row) else ""
        if not sku and not any(_cell_text(row[index[col]]) for col in DROPDOWN_COLUMNS if col in index and index[col] < len(row)):
            continue
        for column in REQUIRED_COLUMNS:
            pos = index.get(column)
            if pos is None:
                highlights.append({"row": excel_row, "column": column, "message": "缺少这一列"})
                continue
            text = _cell_text(row[pos]) if pos < len(row) else ""
            if column in DROPDOWN_COLUMNS:
                if not text:
                    text = "空"
                choices = allowed.get(column) or set()
                if text not in choices:
                    highlights.append({"row": excel_row, "column": column, "message": f"不在官方下拉项里：{text}"})
                continue
            if not text:
                highlights.append({"row": excel_row, "column": column, "message": "必填项为空"})
        for column in DROPDOWN_COLUMNS:
            if column in REQUIRED_COLUMNS or column not in index:
                continue
            pos = index[column]
            text = _cell_text(row[pos]) if pos < len(row) else ""
            if not text:
                text = "空"
            choices = allowed.get(column) or set()
            if text not in choices:
                highlights.append({"row": excel_row, "column": column, "message": f"不在官方下拉项里：{text}"})
    return highlights


def precheck_sta_bytes(data: bytes, dropdowns: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    wb = load_workbook(BytesIO(data), data_only=True)
    ws = wb.active
    rows = [[cell.value for cell in row] for row in ws.iter_rows()]
    return precheck_sta_rows(rows, dropdowns)
