from __future__ import annotations

from io import BytesIO
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from fba_tool.user_config import param
from fba_tool.template_loader import templates_dir

TEMPLATE_FILENAME = "发货录入样表.xlsx"
SHEET_NAME = "发货录入"

HEADERS = [
    "SKU简称",
    "FNSKU",
    "发货总数",
    "单箱装量",
    "箱长(cm)",
    "箱宽(cm)",
    "箱高(cm)",
    "单个重量(kg)",
    "空纸箱重(kg)",
    "单箱毛重(kg)",
]

REQUIRED_MARKS = {0, 2, 3, 4, 5, 6}  # column indexes that are required

EXAMPLE_ROWS = [  # S9-step5：示例行只用 DEMO 值（不含真实 SKU / FNSKU）
    ["DEMO-SKU-001", "X0DEMO0001", 90, 6, 51, 29.5, 38, 2.5, 0.5, 16.5],
    ["DEMO-SKU-002", "X0DEMO0002", 40, 4, 51, 29.5, 38, 3.0, 0.5, ""],
    ["DEMO-SKU-003", "X0DEMO0003", 180, 3, 51, 29.5, 38, 3.2, 0.5, ""],
    ["DEMO-SKU-004", "X0DEMO0004", 60, 6, 51, 29.5, 38, 2.5, 0.5, ""],
    ["DEMO-SKU-005", "X0DEMO0005", 20, 4, 51, 29.5, 38, 3.0, 0.5, ""],
    ["DEMO-SKU-006", "X0DEMO0006", 90, 3, 51, 29.5, 38, 3.2, 0.5, ""],
]

INSTRUCTION = (
    "填写说明：带*为必填。SKU简称填亚马逊SKU；发货总数/单箱装量/箱规(cm)必填。"
    "重量可留空由系统估算；单箱毛重可留空则按「单个重量×装量+空纸箱重」计算。"
    "示例行可删改，也可在下方空白行继续追加。"
)


def template_file_path() -> Path:
    return templates_dir() / TEMPLATE_FILENAME


def ensure_template_on_disk() -> Path:
    path = template_file_path()
    if not path.exists():
        path.write_bytes(generate_input_template_bytes())
    return path


def generate_input_template_bytes(include_examples: bool | None = None) -> bytes:
    if include_examples is None:
        include_examples = bool(param("input_template_include_example", False))
    blank_rows = int(param("input_template_blank_rows", 10))
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(HEADERS))
    note = ws.cell(row=1, column=1, value=INSTRUCTION)
    note.font = Font(size=10, color="444444")
    note.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[1].height = 36

    header_row = 2
    header_fill = PatternFill("solid", fgColor="FFF3E0")
    header_font = Font(bold=True)
    for col, name in enumerate(HEADERS, start=1):
        label = f"{name}*" if (col - 1) in REQUIRED_MARKS else name
        cell = ws.cell(row=header_row, column=col, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[get_column_letter(col)].width = 16 if col <= 2 else 12

    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 14

    start = header_row + 1
    rows = EXAMPLE_ROWS if include_examples else []
    for i, data in enumerate(rows):
        for col, val in enumerate(data, start=1):
            ws.cell(row=start + i, column=col, value=val)

    for i in range(len(rows), len(rows) + blank_rows):
        ws.cell(row=start + i, column=1, value="")

    ws.freeze_panes = "A3"
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


def load_template_from_disk() -> bytes:
    path = ensure_template_on_disk()
    return path.read_bytes()
