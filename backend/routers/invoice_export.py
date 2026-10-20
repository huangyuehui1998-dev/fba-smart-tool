"""S4-fix1 发票按货代模板导出：预览（拦截项/警告/箱号区间）和导出 xlsx。只读产品库与仓库地址库，不写库。"""
from __future__ import annotations

import io
import json
from typing import Any, Dict, Optional
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter()


@router.get("/api/invoice-export/forwarders")
def api_export_forwarders():
    from fba_tool.invoice_export import ExportConfigError, export_forwarders

    try:
        return {"forwarders": [{"id": k, "name": v.get("name", ""), "adapter": v["export_adapter"]} for k, v in export_forwarders().items()]}
    except ExportConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class WarehouseUndecided(ValueError):
    """配送地址对应多个/没有仓库，且 CSV 里的仓库代码也定不下来：返回候选给界面选。"""

    def __init__(self, message: str, candidates):
        super().__init__(message)
        self.candidates = list(candidates)


def _undecided(exc: "WarehouseUndecided"):
    return JSONResponse(status_code=422, content={"detail": str(exc), "warehouse_candidates": exc.candidates})


def _adapter_of(forwarder_id: str) -> str:
    from fba_tool.invoice_export import export_forwarders

    try:
        return export_forwarders().get(forwarder_id, {}).get("export_adapter", "")
    except Exception:  # noqa: BLE001
        return ""


def warehouse_conflict_warning(code: str, source: str, csv_code: str, ship_to: str):
    """S8 P1（S7 待办 A）：最终仓库和 CSV 仓库代码不一致时提示（界面手选 / 配送地址唯一对应 都可能和 CSV 不同）。"""
    cc = (csv_code or "").strip().upper()
    if not code or cc in ("", "UNKN") or cc == code:
        return None
    why = {"界面指定": "你在面板上选的仓库", "配送地址": f"按配送地址「{ship_to}」查到的仓库"}.get(source, f"按{source}定的仓库")
    return {"code": "warehouse_csv_conflict", "csv_code": cc, "warehouse": code,
            "message": f"{why} {code} 和货件 CSV 里的仓库代码 {cc} 不一致，发票按 {code} 填写，请核对是否选错仓库"}


def resolve_export_warehouse(forwarder_id: str, explicit: str, ship_to: str, csv_code: str):
    """仓库取值（S7-fix1）：① 界面指定 ② 配送地址唯一对应 ③ 配送地址对应多个时，用 CSV 里的仓库代码（货件名称等，须在候选内）
    ④ 地址库查不到时，CSV 仓库代码若在地址库里有也可用。返回 (code, source)。"""
    from fba_tool.invoice_templates import _ship_to_codes
    from fba_tool.warehouse_db import get_warehouse, list_warehouse_codes

    code = (explicit or "").strip().upper()
    if code:
        return code, "界面指定"
    codes = _ship_to_codes(ship_to)
    cc = (csv_code or "").strip().upper()
    if cc == "UNKN":
        cc = ""
    if len(codes) == 1:
        return codes[0], "配送地址"
    if cc and cc in codes:
        return cc, "CSV 仓库代码（配送地址同城多仓）"
    if not codes and cc and get_warehouse(cc):
        return cc, "CSV 仓库代码"
    if forwarder_id == "send" or _adapter_of(forwarder_id) == "send":  # SEND 发票不写派送地址
        return "", ""
    cands = codes or list_warehouse_codes(whitelist_only=True)
    msg = (f"货件 CSV 配送地址「{ship_to}」" + (f"对应多个仓库：{'、'.join(codes)}" if codes else "在仓库地址库里找不到")
           + (f"，CSV 仓库代码 {cc} 也不在其中" if cc else "") + "，请在面板上选择仓库")
    raise WarehouseUndecided(msg, cands)


async def _run(forwarder_id, csv_file, reference_id, order_no, channel, invoice_date, warehouse, measured_file, box_id_fix,
               weight_basis="", weight_ref_file=None):
    from fba_tool.invoice_export import export_invoice
    from fba_tool.invoice_rules import read_jiufang_box_data
    from fba_tool.invoice_templates import _ship_to_codes
    from fba_tool.master_db import lookup_by_fnsku
    from fba_tool.shipment_parser import parse_csv_shipment
    from fba_tool.warehouse_db import get_warehouse

    from fba_tool.invoice_export import get_export_forwarder

    get_export_forwarder(forwarder_id)  # S8 D14：先校验货代，未知货代直接报“不支持该货代”
    csv_bytes = await csv_file.read()
    s = parse_csv_shipment(csv_bytes, file_name=csv_file.filename or "", allow_unassigned_fba=True)
    # S8-fix1 N2：重量口径 = 用户在面板选的 > 上传的货代原件按 CSV 核对判定 > 货代配置；都没有就留空并提示
    wb_basis, wb_src = (weight_basis or "").strip() or None, "面板选择" if (weight_basis or "").strip() else ""
    wb_note = None
    if wb_basis is None and weight_ref_file is not None:
        from fba_tool.invoice_export import decide_weight_basis

        wb_basis, wb_src = decide_weight_basis(await weight_ref_file.read(), weight_ref_file.filename or "", csv_bytes, s.shipment_id)
        if wb_basis is None:
            wb_note = {"code": "weight_basis_ref_undecided", "message": wb_src}
            wb_src = ""
    products: Dict[str, Any] = {}
    for f in {str(x).upper() for x in s.box_items["FNSKU"]}:
        p = lookup_by_fnsku(f)
        if p:
            products[f] = p
    code, wh_source = resolve_export_warehouse(forwarder_id, warehouse, s.ship_to, s.warehouse_code)
    measured = None
    if measured_file is not None:
        fix = json.loads(box_id_fix) if box_id_fix else None
        measured = read_jiufang_box_data(await measured_file.read(), s.shipment_id, measured_file.filename or "", box_id_fix=fix)
    res = export_invoice(forwarder_id, shipment=s, products=products, reference_id=reference_id or "", warehouse=code,
                         warehouse_info=get_warehouse(code) if code else None, order_no=order_no or "", channel=channel or "",
                         invoice_date=invoice_date or None, measured=measured,
                         weight_basis=wb_basis, weight_basis_source=wb_src)
    if wb_note:
        res["warnings"].append(wb_note)
    res["warehouse_source"] = wh_source
    conflict = warehouse_conflict_warning(code, wh_source, s.warehouse_code, s.ship_to)
    if conflict:
        res["warnings"].append(conflict)
    return res


def _blocked(exc):
    return JSONResponse(status_code=409, content={"detail": str(exc), "blocking": exc.blocking})


@router.post("/api/invoice-export/preview")
async def api_export_preview(forwarder_id: str = Form(...), csv_file: UploadFile = File(...), reference_id: str = Form(""),
                             order_no: str = Form(""), channel: str = Form(""), invoice_date: str = Form(""), warehouse: str = Form(""),
                             measured_file: Optional[UploadFile] = File(None), box_id_fix: str = Form(""),
                             weight_basis: str = Form(""), weight_ref_file: Optional[UploadFile] = File(None)):
    from fba_tool.invoice_rules import InvoiceBlocked

    try:
        res = await _run(forwarder_id, csv_file, reference_id, order_no, channel, invoice_date, warehouse, measured_file, box_id_fix,
                         weight_basis, weight_ref_file)
    except InvoiceBlocked as exc:
        return _blocked(exc)
    except WarehouseUndecided as exc:
        return _undecided(exc)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    m = res["model"]
    return {"file_name": res["file_name"], "shipment_id": m.shipment_id, "warehouse": m.warehouse,
            "warehouse_source": res.get("warehouse_source", ""), "warnings": res["warnings"],
            "price_sources": m.price_sources, "box_count": len(m.boxes), "total_qty": m.total_qty, "total_value": m.total_value,
            "ranges": [{"box": r.label, "fnsku": r.fnsku, "qty": r.qty, "weight": r.weight, "mixed": r.mixed} for r in m.ranges],
            "lines": [{k: l[k] for k in ("fnsku", "qty", "price", "price_source", "total")} for l in m.lines]}


@router.post("/api/invoice-export/export")
async def api_export_file(forwarder_id: str = Form(...), csv_file: UploadFile = File(...), reference_id: str = Form(""),
                          order_no: str = Form(""), channel: str = Form(""), invoice_date: str = Form(""), warehouse: str = Form(""),
                          measured_file: Optional[UploadFile] = File(None), box_id_fix: str = Form(""),
                             weight_basis: str = Form(""), weight_ref_file: Optional[UploadFile] = File(None)):
    from fba_tool.invoice_rules import InvoiceBlocked

    try:
        res = await _run(forwarder_id, csv_file, reference_id, order_no, channel, invoice_date, warehouse, measured_file, box_id_fix,
                         weight_basis, weight_ref_file)
    except InvoiceBlocked as exc:
        return _blocked(exc)
    except WarehouseUndecided as exc:
        return _undecided(exc)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StreamingResponse(io.BytesIO(res["bytes"]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(res['file_name'])}",
                                      "X-Invoice-Warnings": quote(json.dumps([w["code"] for w in res["warnings"]]))})
