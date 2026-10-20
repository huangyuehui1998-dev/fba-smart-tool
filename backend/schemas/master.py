"""产品主数据库相关请求契约。"""
from __future__ import annotations

from typing import Any, List

from pydantic import BaseModel, Field


class MasterResolveRequest(BaseModel):
    skus: List[str] = Field(default_factory=list)


class MasterSkuPatchRequest(BaseModel):
    field: str = Field(..., min_length=1, description="要更新的字段名")
    value: Any = Field(None, description="新值")
