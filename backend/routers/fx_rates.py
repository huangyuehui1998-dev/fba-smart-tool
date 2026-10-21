"""汇率录入。customs_monthly 的来源说明固定为署令第 272 号第十三条。"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from fba_tool.fx_rates import (
    CUSTOMS_MONTHLY_SOURCE,
    TAX_FX_CHOICES,
    delete_rate,
    import_csv,
    list_rates,
    upsert_rate,
)

router = APIRouter()


@router.get("/api/fx-rates")
def api_list_fx_rates():
    return {
        "items": list_rates(),
        "customs_monthly_source": CUSTOMS_MONTHLY_SOURCE,
        "tax_fx_choices": list(dict.fromkeys(TAX_FX_CHOICES.values())),
    }


@router.put("/api/fx-rates")
def api_put_fx_rate(body: dict):
    try:
        return upsert_rate(body or {})
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/api/fx-rates/{rate_id}")
def api_delete_fx_rate(rate_id: int):
    if not delete_rate(rate_id):
        raise HTTPException(status_code=404, detail="汇率不存在")
    return {"ok": True, "id": rate_id}


@router.post("/api/fx-rates/import")
async def api_import_fx_rates(file: UploadFile = File(...)):
    try:
        return import_csv(await file.read())
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
