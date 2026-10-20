"""Step 5 报关资料 API 契约。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CustomsPreviewRequest(BaseModel):
    source: str = Field("shipment", description="invoice(A) | shipment(B)")
    exporter_id: Optional[str] = None
    order_no: str = ""
    dates: Optional[Dict[str, str]] = None
    overrides: Optional[Dict[str, Any]] = None
    workflow_json: Optional[Dict[str, Any]] = None
    invoice_draft: Optional[Dict[str, Any]] = None
    selected_shipment_ids: Optional[List[str]] = Field(
        None, description="本次报关勾选的 FBA 货件编号；None 或空=全选合并报关"
    )


class CustomsExportRequest(BaseModel):
    source: str = "shipment"
    exporter_id: Optional[str] = None
    order_no: str = ""
    dates: Optional[Dict[str, str]] = None
    overrides: Optional[Dict[str, Any]] = None
    workflow_json: Optional[Dict[str, Any]] = None
    invoice_draft: Optional[Dict[str, Any]] = None
    selected_shipment_ids: Optional[List[str]] = Field(
        None, description="本次报关勾选的 FBA 货件编号；None 或空=全选合并报关"
    )
    data: Optional[Dict[str, Any]] = Field(None, description="前端编辑后的完整预览数据，优先于重算")
    export_format: str = Field("xlsx", description="xlsx | xls（v5 Q15 两种都支持）")


class ExporterProfileBody(BaseModel):
    id: Optional[str] = None
    name: str
    credit_code: str = ""
    address: str = ""
    tel: str = ""
    signed_at: str = "武汉"
    domestic_source: str = "武汉"


class ExporterActiveBody(BaseModel):
    id: str
