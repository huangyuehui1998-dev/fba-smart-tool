"""历史任务相关请求契约。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class TaskHistorySaveRequest(BaseModel):
    snapshot: Dict[str, Any] = Field(..., description="工作流快照 JSON")
    name: Optional[str] = Field(None, description="自定义任务名；留空则用快照内名称")


class TaskHistoryRenameRequest(BaseModel):
    name: str = Field(..., min_length=1, description="新任务名称")
