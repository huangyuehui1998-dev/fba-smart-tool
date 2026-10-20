"""Step 4.5 货代发票相关请求契约。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class InvoiceGenerateRequest(BaseModel):
    shipment_id: str
    csv_base64: str = Field("", description="该货件 CSV 文件 base64；有 parsed_shipment 时可留空")
    pdf_base64: str = Field("", description="该货件 PDF 文件 base64")
    parsed_shipment: Optional[Dict[str, Any]] = Field(
        None,
        description="Step 4 已解析货件结构（优先于 csv_base64 重解析）",
    )
    template_base64: Optional[str] = Field(None, description="发票模板 xlsx base64；不传则读货代或 templates/ 默认")
    forwarder_id: Optional[str] = Field(None, description="货代 ID；优先于 template_base64")
    po_number: Optional[str] = Field("", description="POAnumber，Step 4.5 手填")
    workflow_json: Optional[Dict[str, Any]] = Field(None, description="Step1–4 工作流上下文")
    api_key: Optional[str] = None
    model: Optional[str] = Field(None, description="DeepSeek 模型")
    temperature: Optional[float] = Field(None, ge=0, le=2, description="采样温度 0–2")


class InvoicePreviewRequest(BaseModel):
    template_base64: Optional[str] = Field(None, description="发票模板 xlsx base64")
    forwarder_id: Optional[str] = Field(None, description="货代 ID；优先于 template_base64")


class InvoiceFieldEdit(BaseModel):
    字段: str
    值: Any = ""


class InvoiceExportRequest(BaseModel):
    template_base64: Optional[str] = Field(None, description="发票模板 xlsx base64；与 template_hash 二选一")
    template_hash: Optional[str] = Field(None, description="服务端缓存的模板 SHA256，导出时优先使用")
    forwarder_id: Optional[str] = Field(None, description="货代 ID；优先于 template_base64")
    shipment_id: str
    warehouse_code: str
    template_sheet: str = "Sheet1"
    fields: List[Dict[str, Any]] = Field(..., description="发票字段列表，含 key/label/value/source/cell/required")
