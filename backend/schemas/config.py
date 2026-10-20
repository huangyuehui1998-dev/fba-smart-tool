"""系统配置相关请求契约。"""
from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel


class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, Any]


class FormulasUpdateRequest(BaseModel):
    formulas: Dict[str, Any]
