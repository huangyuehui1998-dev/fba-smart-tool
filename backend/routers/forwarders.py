"""货代档案 CRUD + 模板下载。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from fba_tool.forwarder_registry import (
    create_forwarder,
    decode_template_base64,
    delete_forwarder,
    get_forwarder,
    get_template_bytes,
    list_forwarders,
    replace_forwarder_template,
    update_forwarder,
)
from utils.responses import xlsx_response

router = APIRouter()


class ForwarderCreateBody(BaseModel):
    name: str = Field(..., min_length=1)
    template_base64: str = Field(..., description="发票模板 xlsx base64")


class ForwarderUpdateBody(BaseModel):
    name: Optional[str] = None
    template_base64: Optional[str] = None


@router.get("/api/forwarders")
def api_list_forwarders():
    from fba_tool.forwarder_mapping import list_forwarders_enriched

    return {"forwarders": list_forwarders_enriched()}


@router.get("/api/forwarders/{forwarder_id}")
def api_get_forwarder(forwarder_id: str):
    return get_forwarder(forwarder_id).to_dict()


@router.get("/api/forwarders/{forwarder_id}/template")
def api_get_forwarder_template(forwarder_id: str):
    fwd = get_forwarder(forwarder_id)
    data = get_template_bytes(forwarder_id)
    return xlsx_response(data, fwd.template_file)


@router.post("/api/forwarders")
def api_create_forwarder(body: ForwarderCreateBody):
    profile = create_forwarder(body.name, decode_template_base64(body.template_base64))
    return {"ok": True, "forwarder": profile.to_dict()}


@router.put("/api/forwarders/{forwarder_id}")
def api_update_forwarder(forwarder_id: str, body: ForwarderUpdateBody):
    profile = get_forwarder(forwarder_id)
    if body.name:
        profile = update_forwarder(forwarder_id, name=body.name)
    if body.template_base64:
        profile = replace_forwarder_template(forwarder_id, decode_template_base64(body.template_base64))
    return {"ok": True, "forwarder": profile.to_dict()}


@router.delete("/api/forwarders/{forwarder_id}")
def api_delete_forwarder(forwarder_id: str):
    delete_forwarder(forwarder_id)
    return {"ok": True}
