"""Step 4.5 生成发票与 /api/invoice-export/export 使用同一套货代适配器。

有导出适配器的货代不再按通用表头猜格子。生成时渲染正式发票并记住结果，
导出时直接交这本工作簿；表格里的手改再叠加上去。
"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import openpyxl
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter

from fba_tool.invoice_automation import InvoiceDraft
from fba_tool.univer_apply import (
    ApplyRejected,
    _is_formula,
    _iter_cells,
    _norm_formula,
    _raise_conflicts,
    _slave_map,
    _snapshot_sheets,
    _values_equal,
    _write,
)

REFERENCE_ID_EMPTY_HINT = "Reference ID 为空，请上传货件 PDF"

_CACHE: Dict[str, bytes] = {}


def _key(forwarder_id: str, shipment_id: str) -> str:
    return f"{forwarder_id}\n{shipment_id}"


def remember_render(forwarder_id: str, shipment_id: str, data: bytes) -> None:
    if forwarder_id and shipment_id and data:
        _CACHE[_key(forwarder_id, shipment_id)] = data


def recall_render(forwarder_id: str | None, shipment_id: str | None) -> Optional[bytes]:
    if not forwarder_id or not shipment_id:
        return None
    return _CACHE.get(_key(forwarder_id, shipment_id))


def _adapter_id(forwarder_id: str | None) -> str:
    if not forwarder_id:
        return ""
    from fba_tool.invoice_export import export_forwarders

    return str((export_forwarders().get(forwarder_id) or {}).get("export_adapter") or "")


def render_adapter_invoice(
    forwarder_id: str,
    csv_bytes: bytes,
    parsed_shipment: dict | None = None,
    warehouse: str = "",
) -> Dict[str, Any]:
    """和 /api/invoice-export/export 同一套解析、产品、仓库和适配器。"""
    from fba_tool.invoice_export import export_invoice
    from fba_tool.invoice_table import overlay_csv_asin, overlay_csv_english_name
    from fba_tool.master_db import lookup_by_fnsku
    from fba_tool.shipment_parser import parse_csv_shipment
    from fba_tool.shipment_serialize import resolve_csv_shipment
    from fba_tool.warehouse_db import get_warehouse
    from routers.invoice_export import resolve_export_warehouse

    if csv_bytes:
        ship = parse_csv_shipment(csv_bytes, file_name=f"{forwarder_id}.csv", allow_unassigned_fba=True)
    else:
        ship = resolve_csv_shipment(parsed_shipment=parsed_shipment, csv_bytes=None)
    products: Dict[str, Any] = {}
    fnskus = set()
    if not ship.box_items.empty and "FNSKU" in ship.box_items.columns:
        fnskus = {str(x).upper() for x in ship.box_items["FNSKU"] if str(x or "").strip()}
    for fnsku in fnskus:
        product = lookup_by_fnsku(fnsku)
        if product:
            products[fnsku] = product
    products = overlay_csv_english_name(overlay_csv_asin(products, csv_bytes), csv_bytes)
    code, _source = resolve_export_warehouse(forwarder_id, warehouse or "", ship.ship_to, ship.warehouse_code)
    result = export_invoice(
        forwarder_id,
        shipment=ship,
        products=products,
        reference_id="",
        warehouse=code,
        warehouse_info=get_warehouse(code) if code else None,
        order_no="",
        channel="",
        invoice_date=None,
    )
    result["shipment"] = ship
    return result


def _json_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _slave_coords(ws) -> set:
    slaves = set()
    for merged in ws.merged_cells.ranges:
        if merged.max_row > 20000 or merged.max_col > 512:
            continue
        for row in range(merged.min_row, merged.max_row + 1):
            for col in range(merged.min_col, merged.max_col + 1):
                if (row, col) != (merged.min_row, merged.min_col):
                    slaves.add((row, col))
    return slaves


def preview_cells(template: bytes, rendered: bytes, sheet_name: str) -> List[Dict[str, Any]]:
    """只列出这一张表上和模板不同的主格，供预览铺格。导出仍用渲染好的整本。"""
    blank = openpyxl.load_workbook(io.BytesIO(template))
    filled = openpyxl.load_workbook(io.BytesIO(rendered))
    try:
        if sheet_name not in filled.sheetnames:
            return []
        ws = filled[sheet_name]
        src = blank[sheet_name] if sheet_name in blank.sheetnames else None
        slaves = _slave_coords(ws)
        cells: List[Dict[str, Any]] = []
        max_row = min(ws.max_row or 1, 80)
        max_col = min(ws.max_column or 1, 40)
        for row in ws.iter_rows(min_row=1, max_row=max_row, max_col=max_col):
            for cell in row:
                if isinstance(cell, MergedCell) or (cell.row, cell.column) in slaves:
                    continue
                if _is_formula(cell):
                    continue
                old = src[cell.coordinate].value if src is not None else None
                if _values_equal(old, cell.value):
                    continue
                cells.append(
                    {
                        "cell": cell.coordinate,
                        "value": _json_cell(cell.value),
                        "source": "精准提取",
                        "field_key": cell.coordinate,
                        "required": False,
                    }
                )
        return cells
    finally:
        blank.close()
        filled.close()


def try_adapter_draft(
    forwarder_id: str | None,
    csv_bytes: bytes,
    template_bytes: bytes,
    parsed_shipment: dict | None,
    warehouse: str = "",
) -> Optional[InvoiceDraft]:
    if not _adapter_id(forwarder_id):
        return None
    from fba_tool.xlsx_io import load_workbook_fast

    rendered = render_adapter_invoice(forwarder_id or "", csv_bytes, parsed_shipment, warehouse=warehouse)
    remember_render(forwarder_id or "", rendered["shipment"].shipment_id, rendered["bytes"])
    wb = load_workbook_fast(template_bytes)
    sheet = wb.active.title
    wb.close()
    warnings = []
    for item in rendered.get("warnings") or []:
        if isinstance(item, dict):
            warnings.append(str(item.get("message") or item.get("code") or ""))
        elif item:
            warnings.append(str(item))
    if _adapter_id(forwarder_id) == "send" and not str(rendered.get("reference_id") or "").strip():
        model = rendered.get("model")
        reference = str(getattr(model, "reference_id", "") or "")
        if not reference.strip():
            warnings.append(REFERENCE_ID_EMPTY_HINT)
    return InvoiceDraft(
        shipment_id=rendered["shipment"].shipment_id,
        warehouse_code=rendered["shipment"].warehouse_code or "",
        fields=[],
        template_sheet=sheet,
        table_cells=preview_cells(template_bytes, rendered["bytes"], sheet),
        is_table_mode=True,
        warnings=[w for w in warnings if w],
    )


def export_rendered_workbook(
    forwarder_id: str | None,
    shipment_id: str | None,
    template_bytes: bytes,
    snapshot: Optional[Dict[str, Any]],
) -> Optional[bytes]:
    """有生成结果时导出那本正式发票。快照里多出来的手改写回去，模板残留不覆盖。"""
    rendered = recall_render(forwarder_id, shipment_id)
    if rendered is None:
        return None
    if not snapshot:
        return rendered
    return _apply_user_edits(rendered, template_bytes, snapshot)


def _apply_user_edits(rendered: bytes, template: bytes, snapshot: Dict[str, Any]) -> bytes:
    filled = openpyxl.load_workbook(io.BytesIO(rendered))
    blank = openpyxl.load_workbook(io.BytesIO(template))
    formula_cells: List[str] = []
    slave_cells: List[str] = []
    try:
        by_name = {ws.title: ws for ws in filled.worksheets}
        blank_by_name = {ws.title: ws for ws in blank.worksheets}
        for sheet in _snapshot_sheets(snapshot):
            ws = by_name.get(sheet.get("name"))
            src = blank_by_name.get(sheet.get("name"))
            if ws is None:
                continue
            slaves = _slave_map(ws)
            for row, col, payload in _iter_cells(sheet):
                ref = f"{get_column_letter(col)}{row}"
                snap = payload.get("v")
                if (row, col) in slaves:
                    master = ws.cell(*slaves[(row, col)])
                    if not _values_equal(master.value, snap):
                        slave_cells.append(ref)
                    continue
                cell = ws.cell(row, col)
                template_value = src.cell(row, col).value if src is not None else None
                if _is_formula(cell):
                    snap_f = payload.get("f")
                    if snap_f and _norm_formula(snap_f) == _norm_formula(cell.value):
                        continue
                    if _values_equal(template_value, snap) or (snap_f and _norm_formula(snap_f) == _norm_formula(template_value)):
                        continue
                    if not snap_f and "v" in payload and not _values_equal(cell.value, snap):
                        formula_cells.append(ref)
                    continue
                if "v" not in payload and "f" not in payload:
                    continue
                if _values_equal(cell.value, snap) or _values_equal(template_value, snap):
                    continue
                _write(cell, payload)
        _raise_conflicts(formula_cells, slave_cells)
        buf = io.BytesIO()
        filled.save(buf)
        return buf.getvalue()
    finally:
        filled.close()
        blank.close()


def _sheet_merges(wb) -> Dict[str, tuple]:
    """按规范化表名记下合并范围。多出来的表不算另一份模板。"""
    from fba_tool.invoice_templates import norm

    sheets: Dict[str, tuple] = {}
    for ws in wb.worksheets:
        sheets[norm(ws.title)] = tuple(sorted(str(item) for item in ws.merged_cells.ranges))
    return sheets


def _same_forwarder_template(official, preview) -> bool:
    """官方模板的每一张表都要在上传件里，而且合并范围一致。值可以不同。"""
    left = _sheet_merges(official)
    right = _sheet_merges(preview)
    if not left or not right:
        return False
    return all(name in right and right[name] == merges for name, merges in left.items())


def overlay_preview_edits(base: bytes, official: bytes, preview: bytes) -> bytes:
    """forwarder_id 固定官方模板壳。preview 相对空白官方模板改过的格子写回 base。

    不整本替换：合并、公式、图片、数据验证和隐藏表仍以官方模板或已渲染结果为准。
    上传件和官方模板的表名或合并范围不一致时拒绝。公式格改成纯值时拒绝。
    从属格不能写入。
    """
    if not preview or preview == official:
        return base
    filled = openpyxl.load_workbook(io.BytesIO(base))
    blank = openpyxl.load_workbook(io.BytesIO(official))
    edited = openpyxl.load_workbook(io.BytesIO(preview))
    formula_cells: List[str] = []
    slave_cells: List[str] = []
    try:
        from fba_tool.invoice_templates import norm

        if not _same_forwarder_template(blank, edited):
            raise ApplyRejected(
                "TEMPLATE_MISMATCH",
                [],
                "上传的工作簿与所选货代模板不匹配",
            )
        blank_by = {norm(ws.title): ws for ws in blank.worksheets}
        edited_by = {norm(ws.title): ws for ws in edited.worksheets}
        for ws in filled.worksheets:
            src = blank_by.get(norm(ws.title))
            prev = edited_by.get(norm(ws.title))
            if src is None or prev is None:
                continue
            slaves = _slave_map(ws)
            max_row = min(max(prev.max_row or 1, 1), 200)
            max_col = min(max(prev.max_column or 1, 1), 40)
            for row in prev.iter_rows(min_row=1, max_row=max_row, max_col=max_col):
                for cell in row:
                    if isinstance(cell, MergedCell):
                        continue
                    official_value = src.cell(cell.row, cell.column).value
                    if _values_equal(official_value, cell.value):
                        continue
                    coord = cell.coordinate
                    if (cell.row, cell.column) in slaves:
                        master = ws.cell(*slaves[(cell.row, cell.column)])
                        if not _values_equal(master.value, cell.value):
                            slave_cells.append(coord)
                        continue
                    dest = ws.cell(cell.row, cell.column)
                    if _is_formula(dest) or _is_formula(src.cell(cell.row, cell.column)):
                        formula_cells.append(coord)
                        continue
                    if _values_equal(dest.value, cell.value):
                        continue
                    _write(dest, {"v": _json_cell(cell.value) if isinstance(cell.value, (datetime, date)) else cell.value})
        _raise_conflicts(formula_cells, slave_cells)
        buf = io.BytesIO()
        filled.save(buf)
        return buf.getvalue()
    finally:
        filled.close()
        blank.close()
        edited.close()
