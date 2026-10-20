"""无 Streamlit 依赖的导出封装（供 FastAPI 使用）。"""
from __future__ import annotations

from typing import Dict, Tuple

import pandas as pd

from fba_tool.excel_export import (
    build_box_matrix,
    export_amazon_template,
    export_factory_sheet,
    export_forwarder_quote,
    export_internal_archive,
)
from fba_tool.models import SkuRow


def step3_export_bundle(
    editor_df: pd.DataFrame,
    sku_rows: list[SkuRow],
    fnsku_overrides: dict | None = None,
) -> Tuple[pd.DataFrame, bytes, bytes]:
    fnsku = fnsku_overrides or {}
    matrix = build_box_matrix(editor_df)
    internal = export_internal_archive(editor_df, sku_rows, fnsku_overrides=fnsku)
    amazon = export_amazon_template(editor_df, sku_rows, fnsku_overrides=fnsku)
    return matrix, internal, amazon


def step4_export_bytes(factory_long: pd.DataFrame, forwarder_df: pd.DataFrame) -> Tuple[bytes, bytes]:
    return export_factory_sheet(factory_long), export_forwarder_quote(forwarder_df)
