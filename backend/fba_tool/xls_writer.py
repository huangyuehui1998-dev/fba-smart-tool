"""把 openpyxl 工作簿转成 .xls（BIFF8，xlwt），用于报关资料 .xls 导出（v5 Q15）。

方案 v8 §3.6：.xls 写入用 xlwt 按 7 张表重建（不依赖本机 Excel）。
保留：单元格值（日期写成日期序列号 + yyyy-mm-dd 格式）、合并单元格、列宽、行高、字体（名称/字号/粗斜体/颜色近似）、
对齐（水平/垂直/换行）、边框（线型）、数字格式。图片和条件格式不保留（模板里没有）。
"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import Any, Dict, Tuple

import xlwt
from openpyxl.workbook.workbook import Workbook

_H = {"left": 1, "center": 2, "right": 3, "fill": 4, "justify": 5, "centerContinuous": 6, "distributed": 7}
_V = {"top": 0, "center": 1, "bottom": 2, "justify": 3, "distributed": 4}
_B = {None: 0, "thin": 1, "medium": 2, "dashed": 3, "dotted": 4, "thick": 5, "double": 6, "hair": 7,
      "mediumDashed": 8, "dashDot": 9, "mediumDashDot": 10, "dashDotDot": 11, "mediumDashDotDot": 12, "slantDashDot": 13}
DATE_FMT = "yyyy-mm-dd"


def _num_format(cell, value) -> str:
    if isinstance(value, (datetime, date)):
        fmt = cell.number_format or ""
        return fmt if ("y" in fmt.lower() and "d" in fmt.lower()) else DATE_FMT
    fmt = cell.number_format or "General"
    return fmt


def _style_key(cell, value) -> Tuple:
    f, a, b = cell.font, cell.alignment, cell.border
    return (
        f.name, f.sz, bool(f.b), bool(f.i), bool(f.u), 
        a.horizontal, a.vertical, bool(a.wrap_text),
        b.left.style if b.left else None, b.right.style if b.right else None,
        b.top.style if b.top else None, b.bottom.style if b.bottom else None,
        _num_format(cell, value),
    )


def _make_style(key: Tuple) -> xlwt.XFStyle:
    (fname, fsz, bold, italic, under, hz, vt, wrap, bl, br, bt, bb, numfmt) = key
    st = xlwt.XFStyle()
    font = xlwt.Font()
    font.name = fname or "宋体"
    font.height = int(round(float(fsz or 11) * 20))
    font.bold = bold
    font.italic = italic
    font.underline = 1 if under else 0
    st.font = font
    al = xlwt.Alignment()
    al.horz = _H.get(hz or "", 0)
    al.vert = _V.get(vt or "", 2)
    al.wrap = 1 if wrap else 0
    st.alignment = al
    bd = xlwt.Borders()
    bd.left, bd.right, bd.top, bd.bottom = (_B.get(x, 1) for x in (bl, br, bt, bb))
    st.borders = bd
    st.num_format_str = numfmt or "General"
    return st


def _value(v: Any) -> Any:
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, bool):
        return int(v)
    return v


def workbook_to_xls(wb: Workbook) -> bytes:
    book = xlwt.Workbook(encoding="utf-8")
    styles: Dict[Tuple, xlwt.XFStyle] = {}

    def style_for(cell, value):
        k = _style_key(cell, value)
        if k not in styles:
            styles[k] = _make_style(k)
        return styles[k]

    for ws in wb.worksheets:
        sh = book.add_sheet(ws.title[:31], cell_overwrite_ok=True)
        merged = {}
        covered = set()
        for m in ws.merged_cells.ranges:
            merged[(m.min_row, m.min_col)] = (m.max_row, m.max_col)
            for r in range(m.min_row, m.max_row + 1):
                for c in range(m.min_col, m.max_col + 1):
                    if (r, c) != (m.min_row, m.min_col):
                        covered.add((r, c))
        for row in ws.iter_rows():
            for cell in row:
                r, c = cell.row, cell.column
                if (r, c) in covered:
                    continue
                v = _value(cell.value)
                if v is None and not cell.has_style and (r, c) not in merged:
                    continue
                st = style_for(cell, v)
                if (r, c) in merged:
                    r2, c2 = merged[(r, c)]
                    sh.write_merge(r - 1, r2 - 1, c - 1, c2 - 1, "" if v is None else v, st)
                elif v is None:
                    sh.write(r - 1, c - 1, None, st)
                else:
                    sh.write(r - 1, c - 1, v, st)
        for letter, dim in ws.column_dimensions.items():
            if dim.width:
                from openpyxl.utils import column_index_from_string

                idx = column_index_from_string(letter) - 1
                sh.col(idx).width = min(65535, int(dim.width * 256))
        for idx, dim in ws.row_dimensions.items():
            if dim.height:
                rr = sh.row(idx - 1)
                rr.height_mismatch = True
                rr.height = int(dim.height * 20)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()
