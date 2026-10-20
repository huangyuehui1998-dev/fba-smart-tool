"""xlsx 读写辅助：压缩体积、裁剪无效维度。"""
from __future__ import annotations

import zipfile
from io import BytesIO
from typing import Iterable, Tuple

from openpyxl import Workbook, load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.utils.cell import coordinate_to_tuple


def load_workbook_fast(data: bytes):
    return load_workbook(BytesIO(data), keep_links=False, keep_vba=False)


def save_workbook_compact(wb: Workbook) -> bytes:
    bio = BytesIO()
    wb.save(bio)
    raw = bio.getvalue()
    return recompress_xlsx(raw)


def recompress_xlsx(data: bytes) -> bytes:
    """以更高压缩率重写 xlsx zip，通常可明显减小体积。"""
    in_buf = BytesIO(data)
    if not zipfile.is_zipfile(in_buf):
        return data
    in_buf.seek(0)
    out_buf = BytesIO()
    with zipfile.ZipFile(in_buf, "r") as zin, zipfile.ZipFile(
        out_buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as zout:
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))
    return out_buf.getvalue()


def _cell_has_content(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def sheet_data_bounds(ws, extra_cells: Iterable[str] | None = None) -> Tuple[int, int]:
    max_r, max_c = 1, 1
    for (r, c), cell in ws._cells.items():
        if _cell_has_content(cell.value):
            max_r = max(max_r, r)
            max_c = max(max_c, c)
    for ref in extra_cells or ():
        try:
            r, c = coordinate_to_tuple(str(ref).strip())
            max_r = max(max_r, r)
            max_c = max(max_c, c)
        except ValueError:
            continue
    return max_r, max_c


def compact_invoice_workbook(wb, sheet_name: str, cell_refs: Iterable[str]) -> None:
    """保留目标工作表，裁剪多余行列维度元数据，减小保存体积。"""
    keep = sheet_name if sheet_name in wb.sheetnames else wb.active.title
    for name in list(wb.sheetnames):
        if name != keep:
            wb.remove(wb[name])

    ws = wb[keep]
    refs = list(cell_refs)
    max_r, max_c = sheet_data_bounds(ws, refs)
    pad_r, pad_c = 4, 2
    limit_r = max_r + pad_r
    limit_c = max_c + pad_c

    for r in list(ws.row_dimensions.keys()):
        if r > limit_r:
            del ws.row_dimensions[r]

    for col_key in list(ws.column_dimensions.keys()):
        try:
            idx = column_index_from_string(str(col_key))
        except ValueError:
            continue
        if idx > limit_c:
            del ws.column_dimensions[col_key]

    # 去掉非发票页常见的绘图/图表引用，避免无意义体积
    if hasattr(ws, "_charts"):
        ws._charts = []
    if hasattr(ws, "_images"):
        ws._images = []

    # 让 openpyxl 按实际数据区写 dimension
    _ = get_column_letter(max(limit_c, 1))
