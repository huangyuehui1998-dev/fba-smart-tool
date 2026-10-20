"""本地 Excel 批量编辑：与 SQLite product_master 双向同步。"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from fba_tool.app_paths import app_data_dir
from fba_tool.master_db import list_products, upsert_products
from fba_tool.sku_keys import SkuCaseConflict, sku_key

LOCAL_EXCEL_FILENAME = "产品主数据_批量编辑.xlsx"
SHEET_NAME = "产品主数据"

# (db_field, excel_header)
EXPORT_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ("sku", "SKU"),
    ("asin", "ASIN"),
    ("fnsku", "FNSKU"),
    ("english_name", "英文品名"),
    ("model_name", "中文名称(型号)"),
    ("chinese_name", "商品报关名称"),
    ("hs_code", "海关编码"),
    ("brand", "品牌"),
    ("material", "材质"),
    ("purpose", "用途"),
    ("declared_value", "申报单价"),
    ("unit_length", "单品长(cm)"),
    ("unit_width", "单品宽(cm)"),
    ("unit_height", "单品高(cm)"),
    ("unit_weight", "单品重(kg)"),
    ("carton_length", "外箱长(cm)"),
    ("carton_width", "外箱宽(cm)"),
    ("carton_height", "外箱高(cm)"),
    ("carton_weight", "外箱重(kg)"),
    ("parent_asin", "父ASIN"),
    ("listing_status", "Listing状态"),
    ("fulfillment_channel", "配送方式"),
    ("lingxing_synced_at", "领星同步时间"),
)

_FLOAT_FIELDS = frozenset(
    {
        "declared_value",
        "unit_length",
        "unit_width",
        "unit_height",
        "unit_weight",
        "carton_length",
        "carton_width",
        "carton_height",
        "carton_weight",
    }
)


def _norm_header(text: Any) -> str:
    return re.sub(r"[\s_（）()]+", "", str(text or "")).lower()


def _build_header_aliases() -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    for field, header in EXPORT_COLUMNS:
        aliases[_norm_header(header)] = field
        aliases[_norm_header(field)] = field
    aliases[_norm_header("中文品名")] = "model_name"
    aliases[_norm_header("报关名称")] = "chinese_name"
    return aliases


_HEADER_ALIASES = _build_header_aliases()


def local_excel_path() -> Path:
    return app_data_dir() / LOCAL_EXCEL_FILENAME


def export_master_to_local_excel() -> Tuple[Path, int]:
    """将当前主库全量导出到固定 Excel 路径（覆盖写入）。"""
    products = list_products(limit=10_000)
    rows: List[Dict[str, Any]] = []
    for rec in products:
        row = {header: rec.get(field) for field, header in EXPORT_COLUMNS}
        rows.append(row)
    df = pd.DataFrame(rows, columns=[h for _, h in EXPORT_COLUMNS])
    path = local_excel_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=SHEET_NAME, index=False)
    return path, len(products)


def _launch_file(path: Path) -> None:
    """用系统默认程序打开 Excel 文件。"""
    resolved = str(path.resolve())
    if sys.platform == "win32":
        os.startfile(resolved)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.run(["open", resolved], check=False)
        return
    subprocess.run(["xdg-open", resolved], check=False)


def open_local_master_excel() -> Dict[str, Any]:
    path, rows = export_master_to_local_excel()
    _launch_file(path)
    return {
        "ok": True,
        "path": str(path),
        "rows": rows,
        "message": f"已导出 {rows} 条 SKU 并打开 Excel",
    }


def _map_headers(columns: List[str]) -> Dict[str, str]:
    """excel列名 -> db字段"""
    out: Dict[str, str] = {}
    for col in columns:
        key = _norm_header(col)
        if key in _HEADER_ALIASES:
            out[col] = _HEADER_ALIASES[key]
    return out


def _cell_str(val: Any) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    text = str(val).strip()
    return "" if text.lower() in ("nan", "none") else text


def _cell_float(val: Any) -> Optional[float]:
    text = _cell_str(val)
    if not text:
        return None
    try:
        n = float(text.replace(",", ""))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _dataframe_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    col_map = _map_headers([str(c) for c in df.columns])
    if not col_map:
        raise ValueError("Excel 表头无法识别，请使用「在本地 Excel 批量编辑」重新导出标准模板")
    sku_col = next((c for c, f in col_map.items() if f == "sku"), None)
    if not sku_col:
        raise ValueError("Excel 中缺少 SKU 列")

    records: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        sku = _cell_str(row.get(sku_col))
        if not sku or sku_key(sku) == "sku":
            continue
        rec: Dict[str, Any] = {"sku": sku}
        for excel_col, field in col_map.items():
            if field == "sku":
                continue
            raw = row.get(excel_col)
            if field in _FLOAT_FIELDS:
                rec[field] = _cell_float(raw)
            else:
                rec[field] = _cell_str(raw)
        records.append(rec)
    return records


def sync_local_excel_to_db() -> Dict[str, Any]:
    """读取本地 Excel 当前保存内容，按 SKU Upsert 入主库。"""
    path = local_excel_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"未找到 {LOCAL_EXCEL_FILENAME}，请先点击「在本地 Excel 批量编辑」导出。"
        )
    try:
        df = pd.read_excel(path, sheet_name=0, dtype=object)
    except PermissionError as exc:
        raise PermissionError(
            "无法读取 Excel 文件，请先保存并关闭 Excel 后再点「刷新同步」。"
        ) from exc
    except OSError as exc:
        if getattr(exc, "errno", None) == 13 or "permission" in str(exc).lower():
            raise PermissionError(
                "无法读取 Excel 文件，请先保存并关闭 Excel 后再点「刷新同步」。"
            ) from exc
        raise ValueError(f"读取 Excel 失败：{exc}") from exc

    if df.empty:
        raise ValueError("Excel 为空，没有可同步的数据")

    records = _dataframe_to_records(df)
    if not records:
        raise ValueError("未解析到有效 SKU 行，请确认表头与 SKU 列")

    # S9-step4-fix3：先查只差大小写的冲突，有冲突整批不写（不写一半），接口返回 409
    from fba_tool.master_db import sku_conflicts_for

    conflicts = sku_conflicts_for([r["sku"] for r in records])
    if conflicts:
        first, cands = next(iter(conflicts.items()))
        exc = SkuCaseConflict(first, cands)
        if len(conflicts) > 1:
            exc.args = (f"{exc}（另有 {len(conflicts) - 1} 个 SKU 也有同样的冲突：{'、'.join(list(conflicts)[1:6])}）；整批没有同步",)
        else:
            exc.args = (f"{exc}；整批没有同步",)
        raise exc
    upserted = upsert_products(records, overwrite=True)
    total = len(list_products())
    return {
        "ok": True,
        "parsed": len(records),
        "upserted": upserted,
        "total_in_db": total,
        "path": str(path),
    }
