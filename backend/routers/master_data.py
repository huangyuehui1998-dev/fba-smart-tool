"""产品主数据库:上传/列表/查询/解析。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from fba_tool.master_data_apply import resolve_sku_master_flags
from fba_tool.master_data_parser import detect_report_kind, parse_master_report
from fba_tool.master_db import (
    delete_product_by_sku,
    get_product_by_sku,
    get_products_by_skus,
    list_products,
    patch_product_field,
    upsert_products,
)
from fba_tool.master_local_excel import open_local_master_excel, sync_local_excel_to_db
from fba_tool.product_master_parser import parse_business_product_master
from schemas import MasterResolveRequest, MasterSkuPatchRequest

router = APIRouter()


@router.post("/api/master-data/upload/product-info")
async def api_master_data_upload_product_info(file: UploadFile = File(...)):
    """上传业务《产品信息总表》，正则模糊解析后 Upsert 至 product_master。"""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="文件为空")
    try:
        records, col_map = parse_business_product_master(raw, file.filename or "")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"产品信息表解析失败：{exc}") from exc
    if not records:
        raise HTTPException(status_code=400, detail="未从产品信息表中解析到有效 SKU 行")
    upserted = upsert_products(records)
    from fba_tool.product_fields import SOURCE_MANUAL, set_product_fields

    for record in records:
        cost = record.get("product_cost_cny")
        if cost in (None, ""):
            continue
        set_product_fields(
            record["sku"],
            {"product_cost_cny": cost, "product_cost_currency": "CNY"},
            SOURCE_MANUAL,
        )
    total = len(list_products())
    return {
        "ok": True,
        "parsed": len(records),
        "upserted": upserted,
        "total_in_db": total,
        "column_map": col_map,
    }


@router.post("/api/master-data/upload")
async def api_master_data_upload(
    file: UploadFile = File(...),
    report_type: Optional[str] = Form(None),
):
    """上传亚马逊费用预览 / 库存报告，Upsert 至 product_master。"""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="文件为空")
    kind = report_type or detect_report_kind(file.filename or "", raw)
    if kind not in ("fee_preview", "inventory"):
        raise HTTPException(status_code=400, detail="无法识别报告类型，请指定 report_type")
    try:
        records = parse_master_report(raw, kind, file.filename or "")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"报告解析失败：{exc}") from exc
    if not records:
        raise HTTPException(status_code=400, detail="未从报告中解析到有效 SKU 行")
    upserted = upsert_products(records)
    total = len(list_products())
    return {
        "ok": True,
        "report_type": kind,
        "parsed": len(records),
        "upserted": upserted,
        "total_in_db": total,
    }


@router.patch("/api/master-data/sku/{sku}")
def api_master_data_patch_sku(sku: str, body: MasterSkuPatchRequest, create: bool = False):
    from fba_tool.master_db import resolve_stored_sku
    from fba_tool.sku_keys import SkuCaseConflict

    # S8 D6：PATCH 只改已有 SKU；输错 SKU 不再悄悄新建一条（要新建请带 ?create=true）
    # S9-step4-fix3：只差大小写的多条 → 409（之前查不到返回 404「产品库里没有」）
    try:
        stored = resolve_stored_sku(str(sku or "").strip())
    except SkuCaseConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not create and not stored:
        raise HTTPException(status_code=404, detail=f"产品库里没有 SKU「{sku}」，未保存；如要新建请先导入或使用新建入口")
    try:
        rec = patch_product_field(sku, body.field, body.value)
    except SkuCaseConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return rec


@router.post("/api/master-data/sku/{sku}/confirm-normal-price")
def api_master_data_confirm_normal_price(sku: str, body: dict):
    """S9-step4（D-15）：人工确认正常价（默认是将要申报的价，可改）。校验后写成 confirmed 并记审计日志，S9-B 提示随之消失。"""
    from fba_tool.product_fields import confirm_normal_price
    from fba_tool.sku_keys import SkuCaseConflict

    key = str(sku or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="SKU 不能为空")
    try:
        return {"ok": True, **confirm_normal_price(key, (body or {}).get("price"), str((body or {}).get("note") or ""))}
    except SkuCaseConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/api/master-data/sku/{sku}")
def api_master_data_delete_sku(sku: str):
    key = str(sku or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="SKU 不能为空")
    try:
        ok = delete_product_by_sku(key)
    except ValueError as exc:  # S9-step3：只差大小写的多条，不一次全删
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail=f"SKU 不在主数据库：{key}")
    return {"ok": True, "sku": key}


@router.get("/api/master-data/local-excel/open")
def api_master_data_local_excel_open():
    """导出全量主数据到 app_data 固定 Excel 并用系统默认程序打开。"""
    try:
        return open_local_master_excel()
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"导出或打开 Excel 失败：{exc}（若文件已在 Excel 中打开，请先关闭后重试）",
        ) from exc


@router.post("/api/master-data/local-excel/sync")
def api_master_data_local_excel_sync():
    """读取本地 Excel 保存内容，按 SKU Upsert 同步入主库。"""
    from fba_tool.sku_keys import SkuCaseConflict

    try:
        return sync_local_excel_to_db()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SkuCaseConflict as exc:  # S9-step4-fix3：只差大小写的冲突 → 409（之前被 ValueError 统一成 400）
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"同步失败：{exc}") from exc


@router.get("/api/master-data/list")
def api_master_data_list(customs_status: str = ""):
    """customs_status=missing：只列“缺报关配置”的产品。"""
    from fba_tool.master_db import list_sku_case_conflicts

    items = list_products(customs_status=customs_status)
    # S9-step3：库里只差大小写/全角半角的 SKU 组（旧数据）：不自动合并，界面上提示
    return {"items": items, "count": len(items), "sku_case_conflicts": list_sku_case_conflicts()}


@router.get("/api/master-data/export.xlsx")
def api_master_export():
    """产品库导出 Excel，本地批量改后用 import/edits 导回（D-2026-10-16-03）。"""
    from fba_tool.product_edit import export_products_xlsx
    from utils.responses import xlsx_response

    return xlsx_response(export_products_xlsx(), "产品库.xlsx")


@router.post("/api/master-data/import/edits/preview")
async def api_import_edits_preview(file: UploadFile = File(...)):
    from fba_tool.product_edit import preview_products_edit

    return _import_call(preview_products_edit, await file.read(), file.filename or "")


@router.post("/api/master-data/import/edits/apply")
async def api_import_edits_apply(file: UploadFile = File(...)):
    from fba_tool.product_edit import apply_products_edit

    return _import_call(apply_products_edit, await file.read(), file.filename or "")


@router.post("/api/master-data/import/warehouses/preview")
async def api_import_warehouses_preview(file: UploadFile = File(...)):
    """FBA 仓库地址库导入（琪珞发票模板「！」表，约 476 条）：只预览，不写库。"""
    from fba_tool.warehouse_db import preview_warehouse_import

    return _import_call(preview_warehouse_import, await file.read(), file.filename or "")


@router.post("/api/master-data/import/warehouses/apply")
async def api_import_warehouses_apply(file: UploadFile = File(...)):
    from fba_tool.warehouse_codes import reload_user_warehouse_codes
    from fba_tool.warehouse_db import apply_warehouse_import

    out = _import_call(apply_warehouse_import, await file.read(), file.filename or "")
    reload_user_warehouse_codes()
    return out


@router.get("/api/master-data/warehouses")
def api_warehouses(q: str = ""):
    from fba_tool.warehouse_db import list_warehouses

    items = list_warehouses(q)
    return {"items": items, "count": len(items)}


@router.get("/api/master-data/customs-rule-profile")
def api_rule_profile():
    from fba_tool.warehouse_db import get_default_rule_profile

    return get_default_rule_profile()


@router.post("/api/master-data/customs-rule-profile")
def api_rule_profile_update(body: dict):
    from fba_tool.warehouse_db import update_rule_profile

    try:
        return update_rule_profile(body or {})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/master-data/hs-templates")
def api_hs_templates(category: str = ""):
    from fba_tool.hs_config import list_hs_templates

    items = list_hs_templates(category or None)
    return {"items": items, "count": len(items)}


@router.get("/api/master-data/hs-presets")
def api_hs_presets(category: str = "fishing"):
    """S8：钓具 HS 预设参考（只读；用户确认后再 POST hs-templates 写入）。"""
    from fba_tool.hs_presets import hs_presets

    return hs_presets(category)


@router.post("/api/master-data/hs-templates")
def api_hs_template_upsert(body: dict):
    from fba_tool.hs_config import upsert_hs_template

    try:
        return {"ok": True, "item": upsert_hs_template(body or {})}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/master-data/retail-prices")
def api_retail_prices(body: dict):
    from fba_tool.declared_value import FxRateRequired, parse_listing_table, persist_retail_import

    try:
        rows = body.get("rows")
        if body.get("headers"):
            rows = parse_listing_table(body.get("headers") or [], body.get("table_rows") or [])
        fx_by_pair = body.get("fx_by_pair") or {}
        ignored = "products" in body
        source = "lingxing_mcp" if body.get("source") == "lingxing_mcp" else "lingxing_xlsx"
        if body.get("mcp_error"):
            source = "lingxing_xlsx"
        result = persist_retail_import(
            rows or [],
            source=source,
            fx_by_pair=fx_by_pair,
            ignored_products=ignored,
        )
        if body.get("mcp_error"):
            result["notice"] = "领星同步失败，已用手动导入值"
            result["mcp_error"] = str(body.get("mcp_error"))
        return result
    except FxRateRequired as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/master-data/sku/{sku}")
def api_master_data_sku(sku: str):
    rec = get_product_by_sku(sku)
    if not rec:
        raise HTTPException(status_code=404, detail=f"SKU 不在主数据库：{sku}")
    return rec


@router.post("/api/master-data/resolve-skus")
def api_master_data_resolve_skus(body: MasterResolveRequest):
    skus = [str(s).strip() for s in body.skus if str(s).strip()]
    products = get_products_by_skus(skus)
    flags = resolve_sku_master_flags(skus)
    return {"flags": flags, "products": products}



# ---------------- S2：领星 Listing 导出导入（先预览，再确认写入） ----------------

def _import_call(fn, data: bytes, name: str):
    """S9-step2-fix2 N2：导入出错一律 422，带行号和原始值；不返回 500，也不把内部类名露给用户。"""
    import logging

    try:
        return fn(data, name)
    except ValueError as exc:
        detail = {"message": str(exc)}
        rows = getattr(exc, "errors", None)
        if rows:
            detail["errors"] = rows
        raise HTTPException(status_code=422, detail=detail) from exc
    except Exception as exc:  # noqa: BLE001  ArithmeticError 等：只记日志，用户看到中文提示
        logging.getLogger("fba.import").exception("导入解析失败：%s", name)
        raise HTTPException(status_code=422, detail={"message": "文件内容无法解析，请检查价格、数量等数字格式"}) from exc


@router.post("/api/master-data/retail-prices/upload")
async def api_retail_prices_upload(file: UploadFile = File(...)):
    """领星导出写入产品库。请求体里的 products 不使用。"""
    from fba_tool.declared_value import FxRateRequired, parse_listing_xlsx, persist_retail_import
    from fba_tool.shipment_parser import decode_csv_bytes

    raw = await file.read()
    name = (file.filename or "").lower()
    try:
        if name.endswith((".xlsx", ".xlsm")):
            rows = parse_listing_xlsx(raw)
        else:
            import csv
            import io

            text = decode_csv_bytes(raw)
            reader = csv.reader(io.StringIO(text))
            table = list(reader)
            if not table:
                raise ValueError("文件无法解析")
            from fba_tool.declared_value import parse_listing_table

            rows = parse_listing_table(table[0], table[1:])
        return persist_retail_import(rows, source="lingxing_xlsx" if name.endswith((".xlsx", ".xlsm")) else "lingxing_xlsx")
    except FxRateRequired as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": exc.message}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/master-data/import/listing/preview")
async def api_import_listing_preview(file: UploadFile = File(...)):
    from fba_tool.product_import import preview_listing_import

    return _import_call(preview_listing_import, await file.read(), file.filename or "")


@router.post("/api/master-data/import/listing/apply")
async def api_import_listing_apply(file: UploadFile = File(...)):
    from fba_tool.product_import import apply_listing_import

    return _import_call(apply_listing_import, await file.read(), file.filename or "")



# ---------------- S2：箱规批量导入（v8 E3） ----------------

@router.get("/api/master-data/import/carton/template")
def api_carton_template():
    from fastapi.responses import Response

    from fba_tool.product_import import build_carton_template

    return Response(
        content=build_carton_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''%E7%AE%B1%E8%A7%84%E5%AF%BC%E5%85%A5%E6%A8%A1%E6%9D%BF.xlsx"},
    )


@router.post("/api/master-data/import/carton/preview")
async def api_import_carton_preview(file: UploadFile = File(...)):
    from fba_tool.product_import import preview_carton_import

    return _import_call(preview_carton_import, await file.read(), file.filename or "")


@router.post("/api/master-data/import/carton/apply")
async def api_import_carton_apply(file: UploadFile = File(...)):
    from fba_tool.product_import import apply_carton_import

    return _import_call(apply_carton_import, await file.read(), file.filename or "")
