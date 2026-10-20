"""Step 4 货件校验相关请求契约。"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ShipmentValidateRequest(BaseModel):
    throw_ratio: Optional[float] = Field(None, description="抛重系数，默认读取 user_settings")
