"""Step 2 排箱与 Step 3 导出相关请求契约。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import Field

from schemas.step1 import InputRowsRequest


class BoxEditorRequest(InputRowsRequest):
    box_editor: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="装箱明细行：箱号、来源、SKU简称、数量",
    )
    max_mixed_items: Optional[int] = Field(None, description="混装箱最大 SKU 件数")
    max_weight_kg: Optional[float] = Field(None, description="单箱重量上限 (kg)")


class TailAssignRequest(BoxEditorRequest):
    sku: str
    qty: int = Field(..., ge=1)
    target_box: int = Field(..., ge=1, alias="box_no")

    model_config = {"populate_by_name": True}


class ExportStep3Request(BoxEditorRequest):
    confirm_weight_warnings: bool = False
    fba_id: str = ""
