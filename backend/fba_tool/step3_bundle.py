"""Step 3 一键导出：STA、内部表、装箱单、实操单，打成一个 zip。"""
from __future__ import annotations

import zipfile
from io import BytesIO
from typing import Dict, List, Tuple

import pandas as pd
from openpyxl import Workbook

from fba_tool.export_service import step3_export_bundle
from fba_tool.models import SkuRow
from fba_tool.sta_precheck import precheck_sta_bytes

BUNDLE_NAMES: Tuple[str, ...] = ("STA.xlsx", "内部表.xlsx", "装箱单.xlsx", "实操单.xlsx")


def _sheet_bytes(headers: List[str], data_rows: List[List[object]], title: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = title
    ws.append(headers)
    for row in data_rows:
        ws.append(row)
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


def _packing_rows(editor_df: pd.DataFrame, sku_rows: List[SkuRow]) -> List[List[object]]:
    sku_map = {row.sku: row for row in sku_rows}
    out: List[List[object]] = []
    if editor_df.empty:
        return out
    for _, row in editor_df.iterrows():
        sku = str(row.get("SKU简称") or "")
        src = sku_map.get(sku)
        out.append(
            [
                int(row.get("箱号") or 0),
                sku,
                int(row.get("数量") or 0),
                getattr(src, "length_cm", "") if src else "",
                getattr(src, "width_cm", "") if src else "",
                getattr(src, "height_cm", "") if src else "",
                getattr(src, "carton_gross_kg", "") if src else "",
            ]
        )
    return out


def _practice_rows(editor_df: pd.DataFrame, fnsku: Dict[str, str]) -> List[List[object]]:
    out: List[List[object]] = []
    if editor_df.empty:
        return out
    for _, row in editor_df.iterrows():
        sku = str(row.get("SKU简称") or "")
        out.append([int(row.get("箱号") or 0), sku, fnsku.get(sku, ""), int(row.get("数量") or 0), "贴标"])
    return out


def build_step3_files(
    editor_df: pd.DataFrame,
    sku_rows: List[SkuRow],
    fnsku_overrides: Dict[str, str] | None = None,
) -> Dict[str, bytes]:
    fnsku = fnsku_overrides or {}
    _matrix, internal, sta = step3_export_bundle(editor_df, sku_rows, fnsku)
    packing = _sheet_bytes(
        ["箱号", "SKU", "数量", "箱长(cm)", "箱宽(cm)", "箱高(cm)", "单箱毛重(kg)"],
        _packing_rows(editor_df, sku_rows),
        "装箱单",
    )
    practice = _sheet_bytes(
        ["箱号", "SKU", "FNSKU", "数量", "预处理"],
        _practice_rows(editor_df, fnsku),
        "实操单",
    )
    return {
        "STA.xlsx": sta,
        "内部表.xlsx": internal,
        "装箱单.xlsx": packing,
        "实操单.xlsx": practice,
    }


def build_step3_zip(
    editor_df: pd.DataFrame,
    sku_rows: List[SkuRow],
    fnsku_overrides: Dict[str, str] | None = None,
) -> bytes:
    files = build_step3_files(editor_df, sku_rows, fnsku_overrides)
    bio = BytesIO()
    with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in BUNDLE_NAMES:
            archive.writestr(name, files[name])
    return bio.getvalue()


def precheck_step3_sta(
    editor_df: pd.DataFrame,
    sku_rows: List[SkuRow],
    fnsku_overrides: Dict[str, str] | None = None,
) -> list:
    files = build_step3_files(editor_df, sku_rows, fnsku_overrides)
    return precheck_sta_bytes(files["STA.xlsx"])
