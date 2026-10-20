"""Step 1 录入相关请求契约。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TextParseRequest(BaseModel):
    text: str = Field(..., description="运营描述或表格文本")
    api_key: Optional[str] = Field(None, description="DeepSeek API Key（可选，也可用环境变量 DEEPSEEK_API_KEY）")
    model: Optional[str] = Field(None, description="DeepSeek 模型，如 deepseek-chat / deepseek-reasoner")
    temperature: Optional[float] = Field(None, ge=0, le=2, description="采样温度 0–2")


class InputRowsRequest(BaseModel):
    rows: List[Dict[str, Any]] = Field(..., description="Step1 录入行，列名见 INPUT_COLUMNS")
    fnsku_overrides: Dict[str, str] = Field(default_factory=dict, description="SKU -> FNSKU 覆盖映射")
    transport_mode: str = Field("spd_partnered", description="SPD-合作 / SPD-自选 / LTL-FTL")


class ComputePreviewRequest(InputRowsRequest):
    throw_ratio: Optional[float] = Field(None, description="抛重系数，默认读取 user_settings")
