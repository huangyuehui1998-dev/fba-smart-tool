"""把 Univer 快照里改过的值写回原始 xlsx。

只改不相等的普通单元格。公式格保持原公式；快照把公式换成纯值时拒绝。
合并单元格的从属格拒绝写入。不改数据验证、图片、条件格式和隐藏表。
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


def apply_cell_writes(data: bytes, writes: List[Dict[str, Any]], sheet_name: Optional[str] = None) -> bytes:
    """把导出字段写回原始 xlsx。不删工作表、图片、数据验证或隐藏表。

    合并从属格和公式格改成纯值时拒绝，与 apply_snapshot_values 同一套规则。
    自动填写要直接写主格，不要把从属格坐标交给这里。
    """
    wb = openpyxl.load_workbook(io.BytesIO(data))
    formula_cells: List[str] = []
    slave_cells: List[str] = []
    try:
        if sheet_name and sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
        else:
            ws = wb.active
        slaves = _slave_map(ws)
        for item in writes or []:
            ref = str(item.get("cell") or "").replace("$", "").strip().upper()
            if not ref or item.get("value") in (None, ""):
                continue
            from openpyxl.utils.cell import coordinate_to_tuple

            row, col = coordinate_to_tuple(ref)
            value = item.get("value")
            if (row, col) in slaves:
                master = ws.cell(*slaves[(row, col)])
                if not _values_equal(master.value, value):
                    slave_cells.append(ref)
                continue
            cell = ws.cell(row, col)
            if _is_formula(cell):
                if _norm_formula(value) != _norm_formula(cell.value):
                    formula_cells.append(ref)
                continue
            if _values_equal(cell.value, value):
                continue
            _write(cell, {"v": value})
        _raise_conflicts(formula_cells, slave_cells)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
    finally:
        wb.close()


def apply_snapshot_values(data: bytes, snapshot: Dict[str, Any]) -> bytes:
    wb = openpyxl.load_workbook(io.BytesIO(data))
    formula_cells: List[str] = []
    slave_cells: List[str] = []
    try:
        by_name = {ws.title: ws for ws in wb.worksheets}
        for sheet in _snapshot_sheets(snapshot):
            ws = by_name.get(sheet.get("name"))
            if ws is None:
                continue
            slaves = _slave_map(ws)
            for row, col, payload in _iter_cells(sheet):
                ref = f"{get_column_letter(col)}{row}"
                if (row, col) in slaves:
                    master = ws.cell(*slaves[(row, col)])
                    if not _values_equal(master.value, payload.get("v")):
                        slave_cells.append(ref)
                    continue
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
        _raise_conflicts(formula_cells, slave_cells)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
    finally:
        wb.close()


def _raise_conflicts(formula_cells: List[str], slave_cells: List[str]) -> None:
    if not formula_cells and not slave_cells:
        return
    code = "FORMULA_OVERWRITE" if formula_cells else "MERGED_SLAVE"
    cells = formula_cells or slave_cells
    label = "公式单元格不能改成纯值" if code == "FORMULA_OVERWRITE" else "不能写入合并单元格的从属格"
    raise ApplyRejected(code, cells, f"{label}：{', '.join(cells[:30])}")


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


def _slave_map(ws: Worksheet) -> Dict[tuple, tuple]:
    slaves: Dict[tuple, tuple] = {}
    for mr in ws.merged_cells.ranges:
        if mr.max_row > 20000 or mr.max_col > 512:
            continue
        origin = (mr.min_row, mr.min_col)
        for row in range(mr.min_row, mr.max_row + 1):
            for col in range(mr.min_col, mr.max_col + 1):
                if (row, col) != origin:
                    slaves[(row, col)] = origin
    return slaves


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
