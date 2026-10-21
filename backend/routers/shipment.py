"""Step 4 — 货件解析、三维交叉校验、工人装箱单/财务/货代导出。"""

from __future__ import annotations



from typing import Any, Dict, List, Optional



import pandas as pd

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from fastapi.responses import StreamingResponse



from fba_tool.excel_export import export_forwarder_quote, export_shipping_sheet

from fba_tool.shipping_sheet import build_shipping_sheet_legend

from fba_tool.shipment_validator import parse_uploads

from fba_tool.user_config import throw_ratio

from fba_tool.worker_packing_export import export_worker_packing_list, export_worker_packing_preview

from services.shipment_service import (

    build_validate_response,

    iter_shipment_validation_events,

    parse_workflow_json,

    run_shipment_validation,

    with_batch,

)

from utils.responses import xlsx_response

from utils.serialization import read_uploads



router = APIRouter()





@router.post("/api/shipments/parse")

async def api_shipments_parse(

    csv_files: List[UploadFile] = File(..., description="亚马逊装箱单 CSV，可多选"),

    pdf_files: List[UploadFile] = File(..., description="箱唛 PDF，可多选"),

):

    """解析 CSV/PDF 并返回自动匹配状态（不执行逐箱比对）。"""

    csv_payload = read_uploads(csv_files)

    pdf_payload = read_uploads(pdf_files)

    parsed = parse_uploads(csv_payload, pdf_payload)

    return {

        "status_lines": parsed.status_lines,

        "errors": parsed.errors,

        "csv_shipments": list(parsed.csv_map.keys()),

        "pdf_shipments": list(parsed.pdf_map.keys()),

    }





@router.post("/api/shipments/validate")

async def api_shipments_validate(

    csv_files: List[UploadFile] = File(...),

    pdf_files: List[UploadFile] = File(...),

    throw_ratio_val: Optional[float] = Form(None, alias="throw_ratio"),

    workflow_json: Optional[str] = Form(None),

    batch: Optional[str] = Form(None),

):

    """CSV/PDF 货件配对 + 三维交叉校验，返回工人装箱实操单/货代表预览数据。"""

    csv_payload = read_uploads(csv_files)

    pdf_payload = read_uploads(pdf_files)

    if not csv_payload:

        raise HTTPException(status_code=400, detail="请至少上传一个 CSV")

    if not pdf_payload:

        raise HTTPException(status_code=400, detail="请至少上传一个 PDF")



    wf = with_batch(parse_workflow_json(workflow_json), batch)

    ctx = run_shipment_validation(csv_payload, pdf_payload, wf)

    ratio = float(throw_ratio_val if throw_ratio_val is not None else throw_ratio())

    response = build_validate_response(ctx, ratio)
    from services.shipment_service import write_validation_snapshot

    warning = write_validation_snapshot(ctx)
    if warning:
        response["snapshot_warning"] = warning
    return response





@router.post("/api/shipments/validate/stream")

async def api_shipments_validate_stream(

    csv_files: List[UploadFile] = File(...),

    pdf_files: List[UploadFile] = File(...),

    throw_ratio_val: Optional[float] = Form(None, alias="throw_ratio"),

    workflow_json: Optional[str] = Form(None),

    batch: Optional[str] = Form(None),

):

    """与 /validate 相同，但以 NDJSON 流推送实时进度（event: progress | result）。"""

    csv_payload = read_uploads(csv_files)

    pdf_payload = read_uploads(pdf_files)

    if not csv_payload:

        raise HTTPException(status_code=400, detail="请至少上传一个 CSV")

    if not pdf_payload:

        raise HTTPException(status_code=400, detail="请至少上传一个 PDF")



    wf = with_batch(parse_workflow_json(workflow_json), batch)

    ratio = float(throw_ratio_val if throw_ratio_val is not None else throw_ratio())



    def generate():

        yield from iter_shipment_validation_events(csv_payload, pdf_payload, wf, ratio)



    return StreamingResponse(

        generate(),

        media_type="application/x-ndjson",

        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},

    )





@router.post("/api/export/worker_packing_preview")

async def api_export_worker_packing_preview(body: Dict[str, Any]):

    """从已校验预览快速导出工人装箱实操单（无需重传 CSV/PDF）。"""

    from fba_tool.weight_gate import parse_weight_rows, raise_if_weight_unconfirmed

    raise_if_weight_unconfirmed(
        parse_weight_rows(body.get("weight_rows")),
        bool(body.get("confirm_weight_warnings")),
    )
    preview = body.get("worker_packing_preview") or body.get("rows") or []

    if not preview:

        raise HTTPException(status_code=400, detail="worker_packing_preview 为空")

    labels = body.get("worker_packing_warehouses") or []

    return xlsx_response(

        export_worker_packing_preview(preview, labels or None),

        "工人装箱贴标实操单.xlsx",

    )





@router.post("/api/export/worker_packing_list")

async def api_export_worker_packing_list(

    csv_files: List[UploadFile] = File(...),

    pdf_files: List[UploadFile] = File(...),

    workflow_json: Optional[str] = Form(None),

    confirm_weight_warnings: bool = Form(False),

    weight_rows: Optional[str] = Form(None),

):

    """三维交叉校验通过后，导出工人装箱贴标实操单（重传文件，较慢）。"""

    from fba_tool.weight_gate import parse_weight_rows, raise_if_weight_unconfirmed

    raise_if_weight_unconfirmed(parse_weight_rows(weight_rows), confirm_weight_warnings)

    csv_payload = read_uploads(csv_files)

    pdf_payload = read_uploads(pdf_files)

    if not csv_payload:

        raise HTTPException(status_code=400, detail="请至少上传一个 CSV")

    if not pdf_payload:

        raise HTTPException(status_code=400, detail="请至少上传一个 PDF")



    wf = parse_workflow_json(workflow_json)

    ctx = run_shipment_validation(csv_payload, pdf_payload, wf)

    result = ctx["result"]



    if not result.cross_check_ok or not result.pairs:

        errors = [e for e in result.errors if e.startswith("❌")]

        raise HTTPException(

            status_code=422,

            detail={

                "message": "三维交叉校验未通过，禁止导出工人装箱实操单",

                "errors": errors or result.errors,

            },

        )



    return xlsx_response(

        export_worker_packing_list(result.pairs),

        "工人装箱贴标实操单.xlsx",

    )





@router.post("/api/export/shipping_sheet")

def api_export_shipping_sheet(body: Dict[str, Any]):

    """根据发货表行数据导出 (.xlsx)。"""

    from fba_tool.weight_gate import parse_weight_rows, raise_if_weight_unconfirmed

    raise_if_weight_unconfirmed(
        parse_weight_rows(body.get("weight_rows") or body.get("step1_rows")),
        bool(body.get("confirm_weight_warnings")),
    )
    try:

        rows = body.get("shipping_sheet") or body.get("rows") or []

        shipping_df = pd.DataFrame(rows)

        if shipping_df.empty:

            raise HTTPException(status_code=400, detail="shipping_sheet 为空")

        legend_rows = body.get("shipping_sheet_legend") or []

        if not legend_rows and body.get("step1_rows"):

            legend_rows = build_shipping_sheet_legend(body.get("step1_rows") or [])

        return xlsx_response(export_shipping_sheet(shipping_df, legend_rows), "发货表.xlsx")

    except HTTPException:

        raise

    except Exception as exc:

        raise HTTPException(status_code=500, detail=f"发货表导出失败：{exc}") from exc





@router.post("/api/export/forwarder")

def api_export_forwarder(body: Dict[str, Any]):

    """根据货代表行数据导出货代表 (.xlsx)。"""

    from fba_tool.weight_gate import parse_weight_rows, raise_if_weight_unconfirmed

    raise_if_weight_unconfirmed(
        parse_weight_rows(body.get("weight_rows") or body.get("step1_rows")),
        bool(body.get("confirm_weight_warnings")),
    )
    try:

        rows = body.get("forwarder") or body.get("rows") or []

        forwarder_df = pd.DataFrame(rows)

        if forwarder_df.empty:

            raise HTTPException(status_code=400, detail="forwarder 为空")

        return xlsx_response(export_forwarder_quote(forwarder_df), "货代表.xlsx")

    except HTTPException:

        raise

    except Exception as exc:

        raise HTTPException(status_code=500, detail=f"货代表导出失败：{exc}") from exc

