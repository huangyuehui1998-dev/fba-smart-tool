"""STA 预检：只检查 SKU 明细区。箱信息标签行不报必填项为空。"""
from __future__ import annotations

import json
import logging
import re
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from openpyxl import load_workbook

logger = logging.getLogger("fba_tool.sta_precheck")

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

BOX_LABEL_PREFIXES = (
    "包装箱名称",
    "包装箱重量",
    "包装箱宽度",
    "包装箱长度",
    "包装箱高度",
    "箱号",
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


def _compact(value: Any) -> str:
    return _cell_text(value).replace("：", "").replace(":", "").replace(" ", "").replace("\u3000", "")


def is_box_label(value: Any) -> bool:
    text = _compact(value)
    if not text:
        return False
    return any(text.startswith(_compact(prefix)) for prefix in BOX_LABEL_PREFIXES)


def sku_total_from_rows(rows: List[List[Any]]) -> Optional[int]:
    """第 3 行附近的「SKU 总数：N」。找不到就返回 None，交给空行和标签行截断。"""
    for row in rows[:6]:
        for cell in row:
            text = _compact(cell)
            if "SKU总数" not in text:
                continue
            match = re.search(r"(\d+)", text)
            if match:
                return int(match.group(1))
    return None


def precheck_sta_rows(
    rows: List[List[Any]],
    dropdowns: Dict[str, Any] | None = None,
    known_skus: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """rows 是二维表。只检查表头后的 SKU 明细区，标签行不检查。"""
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
    known: Optional[Set[str]] = None if known_skus is None else {str(sku).strip() for sku in known_skus}
    declared = sku_total_from_rows(rows)
    highlights: List[Dict[str, Any]] = []
    checked = 0
    mismatch = False
    in_detail = True
    for offset, row in enumerate(rows[header_idx + 1 :], start=1):
        excel_row = header_idx + 1 + offset
        lead = _cell_text(row[0]) if row else ""
        blank = not any(_cell_text(cell) for cell in row)
        if in_detail and (blank or is_box_label(lead) or (declared is not None and checked >= declared)):
            if declared is not None and checked != declared:
                mismatch = True
            elif declared is not None and checked >= declared and not blank and not is_box_label(lead):
                mismatch = True
            in_detail = False
        if not in_detail:
            if lead and not is_box_label(lead):
                logger.debug("STA 第 %s 行 SKU %s 不在明细区，跳过", excel_row, lead)
            continue
        checked += 1
        sku = _cell_text(row[index["SKU"]]) if "SKU" in index and index["SKU"] < len(row) else ""
        if known is not None and sku and sku not in known:
            logger.debug("STA 第 %s 行 SKU %s 不在本次录入清单，跳过", excel_row, sku)
            continue
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
    if mismatch:
        highlights.append({
            "row": header_idx + 1,
            "column": "SKU 总数",
            "level": "yellow",
            "message": "SKU 总数与明细行数不一致，已按空行或箱信息标签截断",
        })
    return highlights


def precheck_sta_bytes(data: bytes, dropdowns: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    wb = load_workbook(BytesIO(data), data_only=True)
    ws = wb.active
    rows = [[cell.value for cell in row] for row in ws.iter_rows()]
    return precheck_sta_rows(rows, dropdowns)
