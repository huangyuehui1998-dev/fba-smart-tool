"""S4 发票模板映射：列出模板、自动识别、按模板解析（可手动选择模板，可附货件 CSV 交叉核对）。只读，不写库。"""
from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter()


@router.get("/api/invoice-templates")
def api_invoice_templates():
    from fba_tool.invoice_templates import list_templates

    try:
        return {"templates": list_templates()}
    except ValueError as exc:  # 配置文件坏了：给出哪一行，不要 500
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/invoice-templates/detect")
async def api_invoice_template_detect(file: UploadFile = File(...)):
    from fba_tool.invoice_templates import detect_template

    try:
        return detect_template(await file.read(), file.filename or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/invoice-templates/parse")
async def api_invoice_template_parse(
    file: UploadFile = File(...),
    template_id: Optional[str] = Form(None),
    overrides: Optional[str] = Form(None),
    csv_files: List[UploadFile] = File(default=[]),
    accept: Optional[str] = Form(None),
):
    """accept：用户在预览里确认的修正 id 列表（JSON）。不传 = 只预览，修正不生效。"""
    from fba_tool.invoice_templates import apply_corrections, parse_invoice_file, reconcile_with_csv

    try:
        ov = json.loads(overrides) if overrides else None
        res = parse_invoice_file(await file.read(), file.filename or "", template_id=template_id or None, overrides=ov)
        if csv_files:
            res = reconcile_with_csv(res, [await f.read() for f in csv_files])
        acc = json.loads(accept) if accept else []
        if acc:
            if not csv_files:
                raise ValueError("没有货件 CSV，就没有可确认的修正")
            res = apply_corrections(res, acc)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    res.pop("_raw", None)
    return res
