"""Step 5 — 报关资料预览与导出。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from fba_tool.app_paths import bundled_templates_dir
from fba_tool.customs_export import CustomsExportBlocked, export_customs_package
from fba_tool.customs_package import CustomsPackageData, build_customs_data, pairs_from_workflow
from fba_tool.exporter_profiles import get_active_profile, get_profile
from schemas.customs import CustomsExportRequest, CustomsPreviewRequest
from utils.responses import xlsx_response

router = APIRouter()


def _template_bytes() -> bytes:
    path = bundled_templates_dir() / "customs" / "报关资料模板.xlsx"
    if not path.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"报关资料模板不存在：{path}。请先运行 scripts/convert_customs_template.py",
        )
    return path.read_bytes()


def _resolve_profile(exporter_id: str | None) -> dict:
    if exporter_id:
        return get_profile(exporter_id)
    return get_active_profile()


def _build_from_request(body: CustomsPreviewRequest | CustomsExportRequest) -> CustomsPackageData:
    wf = body.workflow_json or {}
    selected_ids = getattr(body, "selected_shipment_ids", None)
    pairs = pairs_from_workflow(wf, selected_ids)
    if not pairs:
        if selected_ids:
            raise HTTPException(status_code=400, detail="勾选的货件无可用数据：请至少勾选一个有效货件")
        raise HTTPException(status_code=400, detail="缺少货件数据：请先完成 Step 4 校验")
    if body.source == "invoice" and not body.invoice_draft:
        raise HTTPException(status_code=400, detail="来源 A 需要 Step 4.5 发票草稿")

    profile = _resolve_profile(body.exporter_id)
    step1_rows = wf.get("input_rows") or wf.get("rows") or []
    return build_customs_data(
        pairs,
        step1_rows,
        profile,
        source=body.source,
        invoice_draft=body.invoice_draft,
        order_no=body.order_no,
        dates=body.dates,
        overrides=body.overrides,
        selected_shipment_ids=selected_ids,
    )


@router.post("/api/customs/preview")
def api_customs_preview(body: CustomsPreviewRequest):
    data = _build_from_request(body)
    return {"ok": True, "data": data.to_dict()}


@router.post("/api/customs/export")
def api_customs_export(body: CustomsExportRequest):
    from fba_tool.weight_gate import raise_if_weight_unconfirmed

    raise_if_weight_unconfirmed(body.weight_rows, body.confirm_weight_warnings)
    if body.data:
        from fba_tool.customs_package import CustomsLineItem, apply_overrides

        payload = dict(body.data)
        lines_raw = payload.pop("lines", []) or []
        lines = [CustomsLineItem(**ln) if isinstance(ln, dict) else ln for ln in lines_raw]
        fields = {k: v for k, v in payload.items() if k in CustomsPackageData.__dataclass_fields__}
        data = CustomsPackageData(**fields)
        data.lines = lines
        data = apply_overrides(data, body.overrides)
    else:
        data = _build_from_request(body)

    fmt = str(body.export_format or "xlsx").lower().lstrip(".")
    if fmt not in ("xlsx", "xls"):
        raise HTTPException(status_code=400, detail=f"导出格式只能是 xlsx 或 xls：{body.export_format}")
    try:
        out = export_customs_package(data, _template_bytes(), fmt=fmt)
    except CustomsExportBlocked as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    from fba_tool.customs_package import customs_filename
    from utils.responses import file_response

    order = body.order_no or data.order_no or "报关资料"
    if body.order_no and not data.order_no:
        data.order_no = body.order_no
    name = customs_filename(order, list(data.shipment_ids or []), fmt, data.declare_mode or "")
    if fmt == "xls":
        return file_response(out, name, "application/vnd.ms-excel")
    return xlsx_response(out, name)
