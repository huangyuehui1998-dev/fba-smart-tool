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
    warehouse: Optional[str] = Field("", description="同城多仓时界面选定的仓库代码")
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
    template_base64: Optional[str] = Field(
        None,
        description="发票模板 xlsx base64。未选货代时作为模板壳；选了货代时不替换官方模板，只把相对空白模板改过的格子叠到导出结果上",
    )
    template_hash: Optional[str] = Field(None, description="服务端缓存的模板 SHA256，导出时优先使用")
    forwarder_id: Optional[str] = Field(
        None,
        description="货代 ID。选定后导出使用该货代的官方模板壳；template_base64 里的预览改动仍然保留",
    )
    shipment_id: str
    warehouse_code: str
    template_sheet: str = "Sheet1"
    fields: List[Dict[str, Any]] = Field(default_factory=list, description="发票字段列表，含 key/label/value/source/cell/required")
    snapshot: Optional[Dict[str, Any]] = Field(None, description="当前 Univer 工作簿。有快照时整本回填，保留未映射的修改。")
