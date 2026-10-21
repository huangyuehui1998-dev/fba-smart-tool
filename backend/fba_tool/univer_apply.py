"""把 Univer 快照里改过的值写回原始 xlsx。

只改不相等的普通单元格。公式格保持原公式；快照把公式换成纯值时拒绝。
合并从属格写到值的主格（标签右侧那一格）；宽备注里的从属格跳过。
不改数据验证、图片、条件格式和隐藏表。
"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import openpyxl
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet


class ApplyRejected(Exception):
    def __init__(self, code: str, cells: List[str], message: str) -> None:
        super().__init__(message)
        self.code = code
        self.cells = cells
        self.message = message


def _merge_at(ws: Worksheet, row: int, col: int):
    for merged in ws.merged_cells.ranges:
        if merged.max_row > 20000 or merged.max_col > 512:
            continue
        if merged.min_row <= row <= merged.max_row and merged.min_col <= col <= merged.max_col:
            return merged
    return None


def _long_note(value: Any) -> bool:
    text = str(value or "")
    return len(text) > 40 or "\n" in text


def resolve_write_cell(ws: Worksheet, row: int, col: int, new_value: Any) -> Optional[tuple]:
    """从属格改写到值的主格。写不进去的宽备注从属格跳过，不让整张导出失败。

    标签合并（A4:B4「FBA Shipment ID」）的值在合并块右侧的主格 C4。
    值合并（C4:H4，主格为空）直接写主格。宽备注（D5:H5）里的从属格不覆盖备注。
    """
    merged = _merge_at(ws, row, col)
    if merged is None or (row, col) == (merged.min_row, merged.min_col):
        return row, col
    if new_value in (None, ""):
        return None
    origin = (merged.min_row, merged.min_col)
    master_value = ws.cell(*origin).value
    if _values_equal(master_value, new_value):
        return None
    if master_value in (None, ""):
        return origin
    width = merged.max_col - merged.min_col + 1
    if width > 3 or _long_note(master_value):
        return None
    next_col = merged.max_col + 1
    host = _merge_at(ws, row, next_col)
    if host:
        dest = (host.min_row, host.min_col)
        if _long_note(ws.cell(*dest).value):
            return None
        return dest
    return row, next_col


def apply_cell_writes(data: bytes, writes: List[Dict[str, Any]], sheet_name: Optional[str] = None) -> bytes:
    """把导出字段写回原始 xlsx。不删工作表、图片、数据验证或隐藏表。

    合并从属格写到值的主格；宽备注里的从属格跳过。公式格改成纯值时拒绝。
    """
    wb = openpyxl.load_workbook(io.BytesIO(data))
    formula_cells: List[str] = []
    try:
        if sheet_name and sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
        else:
            ws = wb.active
        for item in writes or []:
            ref = str(item.get("cell") or "").replace("$", "").strip().upper()
            if not ref or item.get("value") in (None, ""):
                continue
            from openpyxl.utils.cell import coordinate_to_tuple

            row, col = coordinate_to_tuple(ref)
            value = item.get("value")
            target = resolve_write_cell(ws, row, col, value)
            if target is None:
                continue
            row, col = target
            cell = ws.cell(row, col)
            if _is_formula(cell):
                if _norm_formula(value) != _norm_formula(cell.value):
                    formula_cells.append(ref)
                continue
            if _values_equal(cell.value, value):
                continue
            _write(cell, {"v": value})
        if formula_cells:
            raise ApplyRejected("FORMULA_OVERWRITE", formula_cells, f"公式单元格不能改成纯值：{', '.join(formula_cells[:30])}")
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
    finally:
        wb.close()


def apply_snapshot_values(data: bytes, snapshot: Dict[str, Any]) -> bytes:
    wb = openpyxl.load_workbook(io.BytesIO(data))
    formula_cells: List[str] = []
    try:
        by_name = {ws.title: ws for ws in wb.worksheets}
        for sheet in _snapshot_sheets(snapshot):
            ws = by_name.get(sheet.get("name"))
            if ws is None:
                continue
            for row, col, payload in _iter_cells(sheet):
                ref = f"{get_column_letter(col)}{row}"
                target = resolve_write_cell(ws, row, col, payload.get("v"))
                if target is None:
                    continue
                row, col = target
                cell = ws.cell(row, col)
                if _is_formula(cell):
                    snap_f = payload.get("f")
                    if snap_f and _norm_formula(snap_f) == _norm_formula(cell.value):
                        continue
                    if not snap_f and "v" in payload:
                        formula_cells.append(ref)
                    continue
                if "v" not in payload and "f" not in payload:
                    continue
                if _values_equal(cell.value, payload.get("v")):
                    continue
                _write(cell, payload)
        if formula_cells:
            raise ApplyRejected("FORMULA_OVERWRITE", formula_cells, f"公式单元格不能改成纯值：{', '.join(formula_cells[:30])}")
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
    finally:
        wb.close()


def _snapshot_sheets(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    sheets = snapshot.get("sheets") or {}
    order = snapshot.get("sheetOrder") or list(sheets.keys())
    return [sheets[key] for key in order if key in sheets]


def _iter_cells(sheet: Dict[str, Any]):
    cell_data = sheet.get("cellData") or {}
    for row_key, cols in cell_data.items():
        if not isinstance(cols, dict):
            continue
        row = int(row_key) + 1
        for col_key, payload in cols.items():
            if not isinstance(payload, dict):
                continue
            yield row, int(col_key) + 1, payload


def _is_formula(cell: Any) -> bool:
    if isinstance(cell, MergedCell):
        return False
    if getattr(cell, "data_type", None) == "f":
        return True
    return isinstance(cell.value, str) and cell.value.startswith("=")


def _norm_formula(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("="):
        text = text[1:]
    return text


def _values_equal(orig: Any, snap: Any) -> bool:
    if isinstance(orig, bool) or isinstance(snap, bool):
        return bool(orig) is bool(snap) and type(orig) is type(snap) or (isinstance(orig, bool) and snap in (orig, str(orig)))
    if orig is None:
        return snap in (None, "")
    if type(orig).__name__ in {"CellRichText", "ArrayFormula"}:
        return str(orig) == "" or str(orig) == str(snap) or snap in (None, "")
    if isinstance(orig, datetime):
        text = orig.isoformat()
        snap_text = "" if snap is None else str(snap)
        return snap_text in {text, text.replace("T", " "), orig.strftime("%Y-%m-%d"), orig.strftime("%Y-%m-%d %H:%M:%S")}
    if isinstance(orig, date):
        return str(snap) in {orig.isoformat(), orig.strftime("%Y-%m-%d")}
    if isinstance(orig, (int, float)) and not isinstance(orig, bool):
        try:
            if snap in (None, ""):
                return False
            return float(orig) == float(snap)
        except (TypeError, ValueError):
            return False
    return str(orig) == str(snap)


def _write(cell: Any, payload: Dict[str, Any]) -> None:
    value = payload.get("v")
    kind = payload.get("t")
    if kind == 3 or isinstance(value, bool):
        cell.value = bool(value)
        return
    if kind == 2 or isinstance(value, (int, float)):
        cell.value = value
        return
    cell.value = None if value is None else value
