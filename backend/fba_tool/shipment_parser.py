"""亚马逊 FBA 货件 CSV/PDF 解析：按真实箱号 (U-index) 重排。"""
from __future__ import annotations

import csv
import io
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import pdfplumber

from fba_tool.sku_keys import sku_key
from fba_tool.volume_weight import (
    detect_length_unit,
    detect_weight_unit,
    is_packaging_label,
    normalize_box_spec_row,
)
from fba_tool.warehouse_codes import (
    extract_warehouse_from_text,
    is_valid_warehouse_code,
    normalize_code as normalize_warehouse_code,
)


logger = logging.getLogger(__name__)


class PdfTextError(Exception):
    """PDF 文本无法解析（加密/扫描件/图片型/损坏）时抛出，携带明确原因。"""

FBA_BOX_CODE_RE = re.compile(r"(FBA[A-Z0-9]+)U0*(\d+)\s*$", re.I)
WAREHOUSE_STRICT_RE = re.compile(r"\b([A-Z]{2,4}\d{1,2}|[A-Z]{4})\b")
WAREHOUSE_SUFFIX_RE = re.compile(r"[-_\s]([A-Z]{2,4}\d{1,2}|[A-Z]{4})(?:\.pdf|\.csv|\s*)$", re.I)
WAREHOUSE_BLACKLIST = {"AMZN", "INCH", "MIXED", "UNIT", "CTN", "PCS", "FNSKU", "SKU", "BOX", "QTY"}
BOX_COL_HEADER_RE = re.compile(r"箱子\s*(\d+)")
BOX_QTY_HEADER_RE = re.compile(r"(?:包装箱|箱子)\s*(\d+)")
_STA_BOX_RE = re.compile(r"^P\s*\d+\s*[-–—]\s*B\s*0*(\d+)$", re.I)
_CN_BOX_RE = re.compile(r"^第\s*(\d+)\s*箱$")
QTY_RE = re.compile(r"(?:QTY|数量)[:\s：]*(\d+)", re.I)

FBA_BOX_TOKEN_RE = re.compile(r"FBA[A-Z0-9]+U\d+", re.I)
FNSKU_RE = re.compile(r"\b(X0[A-Z0-9]{8,})\b", re.I)
MIXED_SKU_RE = re.compile(r"mixed\s*sku", re.I)

BoxData = Dict[int, Dict[str, int]]


@dataclass
class PdfBoxPage:
    page_index: int
    shipment_id: str
    fba_box_id: str
    box_no: int
    sku: str = ""
    fnsku: str = ""
    qty: int = 0
    is_mixed: bool = False
    raw_text: str = ""
    warehouse_code: str = ""
    ignored_tokens: List[str] = field(default_factory=list)


def format_box_u_label(box_no: int) -> str:
    return f"U{int(box_no):03d}"


def normalize_fba_box_id(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().upper())


def snapshot_box_id(spec: Any, ids: Optional[Dict[Any, str]] = None) -> str:
    """快照用的箱唛。真正的 FBA…U 优先于包装箱名称（如 P1 - B1）。"""
    from fba_tool.carton_math import is_fba_box_id

    mapping = ids or {}
    box_no = spec.get("箱号") if hasattr(spec, "get") else None
    try:
        numeric: Any = int(box_no)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        numeric = box_no
    raw_values = [
        spec.get("FBA箱号") if hasattr(spec, "get") else None,
        mapping.get(box_no) if hasattr(mapping, "get") else None,
        mapping.get(numeric) if hasattr(mapping, "get") else None,
    ]
    fallback = ""
    for raw in raw_values:
        text = str(raw if raw is not None else "").strip()
        if not text or text.lower() == "nan":
            continue
        normalized = normalize_fba_box_id(text)
        if is_fba_box_id(normalized):
            return normalized
        if not fallback:
            fallback = text
    return fallback


@dataclass
class CsvShipment:
    shipment_id: str
    warehouse_code: str
    box_count: int
    column_to_box: Dict[int, int] = field(default_factory=dict)
    box_data: BoxData = field(default_factory=dict)
    box_items: pd.DataFrame = field(default_factory=pd.DataFrame)
    box_specs: pd.DataFrame = field(default_factory=pd.DataFrame)
    box_fba_ids: Dict[int, str] = field(default_factory=dict)
    # 包装箱名称（如 P1 - B34）。不写入 box_fba_ids / FBA箱号。
    box_names: Dict[int, str] = field(default_factory=dict)
    sku_fnsku: Dict[str, str] = field(default_factory=dict)
    # 仓库代码从哪来：货件名称 / 文件名 / CSV头部；空 = 没识别出（UNKN）。界面上可据此标“来自文件名”
    warehouse_source: str = ""
    # CSV 头部“配送地址”原文（如 'BLOOMINGTON, CA'）；S4-fix1 发票核对用它对 FBA 仓库地址库，不用货件名称
    ship_to: str = ""


@dataclass
class PdfShipment:
    shipment_id: str
    page_count: int
    box_data: BoxData = field(default_factory=dict)
    box_items: pd.DataFrame = field(default_factory=pd.DataFrame)
    pages: List[PdfBoxPage] = field(default_factory=list)


CSV_ENCODINGS = ("utf-8-sig", "utf-8", "gbk")


def decode_csv_bytes(file_bytes: bytes) -> str:
    """按 UTF-8-SIG → UTF-8 → GBK 依次严格解码；都失败时明确报编码问题（D4）。"""
    for enc in CSV_ENCODINGS:
        try:
            return file_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        "CSV 文件编码无法识别（已尝试 UTF-8-SIG、UTF-8、GBK）。"
        "请在 Excel 里“另存为 → CSV UTF-8(逗号分隔)”后重新上传。"
    )


def parse_csv_shipment(
    file_bytes: bytes,
    allow_unassigned_fba: bool = False,
    file_name: str = "",
) -> CsvShipment:
    text = decode_csv_bytes(file_bytes)
    rows = list(csv.reader(io.StringIO(text)))

    shipment_id = _csv_meta(rows, "货件编号")
    shipment_name = _csv_meta(rows, "货件名称")
    # 仓库取值顺序：货件名称 → 文件名 → 其余头部字段（跳过工作流程 ID 等 UUID 字段）
    warehouse, warehouse_source = "", ""
    for cand, label in (
        (_warehouse_from_name(shipment_name), "货件名称"),
        (_warehouse_from_filename(file_name), "文件名"),
        (_warehouse_from_name(_scan_text(rows)), "CSV头部"),
    ):
        if cand:
            warehouse, warehouse_source = cand, label
            break
    box_count = _to_int(_csv_meta(rows, "箱子数量"))

    header_idx, box_start = _find_sku_header(rows)
    column_to_box = _build_column_to_box_map(rows, box_start, allow_unassigned_fba)
    if not column_to_box:
        raise ValueError("CSV 未找到「箱号」行或 FBA...U 映射，无法建立真实箱号对应关系。")

    box_data = _extract_box_data(rows, header_idx, box_start, column_to_box)
    sku_fnsku = _extract_sku_fnsku_map(rows, header_idx)
    box_items = _box_data_to_items_df(box_data, warehouse, sku_fnsku)
    box_specs = pd.DataFrame(_extract_box_specs(rows, warehouse, box_start, column_to_box))
    box_fba_ids = _extract_fba_box_ids(rows, box_start, column_to_box)
    box_names = _extract_box_names(rows, column_to_box)

    if box_count <= 0 and box_data:
        box_count = max(box_data.keys())

    return CsvShipment(
        shipment_id=(shipment_id or "UNKNOWN").upper(),
        warehouse_code=warehouse or "UNKN",
        warehouse_source=warehouse_source,
        ship_to=_csv_meta(rows, "配送地址") or "",
        box_count=box_count,
        column_to_box=column_to_box,
        box_data=box_data,
        box_items=box_items,
        box_specs=box_specs,
        box_fba_ids=box_fba_ids,
        box_names=box_names,
        sku_fnsku=sku_fnsku,
    )


def parse_pdf_shipment(file_bytes: bytes) -> PdfShipment:
    pages = parse_pdf_pages(file_bytes)
    shipment_id = ""
    records: List[Dict] = []
    box_data: BoxData = defaultdict(dict)

    for page in pages:
        if page.shipment_id and not shipment_id:
            shipment_id = page.shipment_id
        if page.box_no <= 0:
            continue
        if page.sku and page.qty > 0 and not page.is_mixed:
            records.append({"箱号": page.box_no, "SKU": page.sku, "数量": page.qty})
            box_data[page.box_no][page.sku] = page.qty

    pdf_fnsku = {
        str(p.sku).strip(): str(p.fnsku).strip().upper()
        for p in pages
        if str(p.sku or "").strip() and str(p.fnsku or "").strip()
    }
    return PdfShipment(
        shipment_id=(shipment_id or "UNKNOWN").upper(),
        page_count=len(pages) if pages else 0,
        box_data={k: dict(v) for k, v in sorted(box_data.items())},
        box_items=_box_data_to_items_df(box_data, warehouse="", sku_fnsku=pdf_fnsku),
        pages=pages,
    )


def parse_pdf_pages(file_bytes: bytes) -> List[PdfBoxPage]:
    pages: List[PdfBoxPage] = []
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for idx, page in enumerate(pdf.pages):
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                parsed = _parse_pdf_page_text(text, idx)
                if parsed:
                    pages.append(parsed)
    except Exception:
        return []
    return pages


def _parse_pdf_page_text(text: str, page_index: int) -> Optional[PdfBoxPage]:
    if not text.strip():
        return None

    flat = text.replace("\n", " ")
    shipment_id, box_no = _extract_fba_box_code(flat)
    if box_no <= 0:
        shipment_id, box_no = _extract_fba_box_code(text)

    fba_box_id = ""
    for token in FBA_BOX_TOKEN_RE.findall(text.upper()):
        sid, bno = _extract_fba_box_code(token)
        if bno > 0:
            fba_box_id = token.upper()
            if not shipment_id and sid:
                shipment_id = sid
            if box_no <= 0:
                box_no = bno
            break

    if box_no <= 0:
        return None

    is_mixed = bool(MIXED_SKU_RE.search(text))
    sku = "" if is_mixed else _extract_pdf_sku(text)
    qty = 0 if is_mixed else _extract_pdf_qty(text)
    fnsku_m = FNSKU_RE.search(text)
    fnsku = fnsku_m.group(1).upper() if fnsku_m else ""

    warehouse_code, _wh_warnings = warehouse_from_label_text(text)
    ignored = _ignored_warehouse_tokens(text)

    return PdfBoxPage(
        page_index=page_index,
        shipment_id=(shipment_id or "").upper(),
        fba_box_id=fba_box_id,
        box_no=box_no,
        sku=sku,
        fnsku=fnsku,
        qty=qty,
        is_mixed=is_mixed,
        raw_text=text,
        warehouse_code=warehouse_code,
        ignored_tokens=ignored,
    )


def extract_pdf_shipment_id(file_bytes: bytes) -> str:
    return parse_pdf_shipment(file_bytes).shipment_id


def _norm_csv_cell(value: object) -> str:
    return str(value or "").replace("\xa0", " ").replace("\u3000", " ").strip()


def _label_key(cell: object) -> str:
    return _norm_csv_cell(cell).strip(":").strip("：").lower().replace(" ", "")


def _is_box_id_label(cell: object) -> bool:
    """能用来给列编号的行：真箱号，或 STA 包装箱名称。"""
    text = _label_key(cell)
    if text in {"箱号", "编号", "boxid", "箱子名称"}:
        return True
    return text.startswith("包装箱名称")


def _is_classic_box_label(cell: object) -> bool:
    """5457ff7 写 FBA 箱号的行：箱号 / 编号。箱子名称、包装箱名称不是。"""
    return _label_key(cell) in {"箱号", "编号", "boxid"}


def _is_fba_mark_label(cell: object) -> bool:
    """箱号或箱子名称。包装箱名称不是箱号。箱子名称里的 P1 - Bxx 只当箱名。"""
    return _label_key(cell) in {"箱号", "编号", "boxid", "箱子名称"}


def _is_packaging_name_label(cell: object) -> bool:
    return _label_key(cell).startswith("包装箱名称")


def _labeled_cells(rows: List[List[str]], column_to_box: Dict[int, int], predicate) -> Dict[int, str]:
    """按列记下某一类标签行的原文。后面的同类行覆盖前面的，另一类标签不会进来。"""
    found: Dict[int, str] = {}
    sorted_cols = sorted(column_to_box)
    for row in rows:
        if not row or not sorted_cols or len(row) <= min(sorted_cols):
            continue
        if not predicate(_row_packaging_label(row)):
            continue
        for col_idx in sorted_cols:
            cell = str(row[col_idx]).strip() if col_idx < len(row) else ""
            if not cell or cell.lower() == "nan":
                continue
            found[col_idx] = cell
    return found


def _cell_box_no(cell: object) -> int:
    text = _norm_csv_cell(cell)
    if not text:
        return 0
    named = _STA_BOX_RE.match(text) or _CN_BOX_RE.match(text)
    if named:
        return int(named.group(1))
    return _fba_suffix_to_box_no(text)


def _box_value_start(row: List[str], box_start: int) -> int:
    for idx, cell in enumerate(row):
        if _is_box_id_label(cell):
            return idx + 1
    return box_start


def _build_column_to_box_map(rows: List[List[str]], box_start: int, allow_unassigned: bool = False) -> Dict[int, int]:
    mapping: Dict[int, int] = {}
    box_id_row = _find_box_id_row(rows, box_start)
    if not box_id_row:
        return mapping

    start = _box_value_start(box_id_row, box_start)
    box_index = 1
    for col_idx, cell in enumerate(box_id_row):
        if col_idx < start:
            continue
        cell_str = _norm_csv_cell(cell)
        box_no = _cell_box_no(cell_str)
        if box_no > 0:
            mapping[col_idx] = box_no
        elif allow_unassigned and cell_str == "待分配":
            mapping[col_idx] = box_index
        box_index += 1
    return mapping


def _find_box_id_row(rows: List[List[str]], box_start: int) -> List[str] | None:
    best_row = None
    best_score = 0
    for row in rows:
        if not row:
            continue
        start = _box_value_start(row, box_start)
        if len(row) <= start and not any(_is_box_id_label(cell) for cell in row):
            continue
        classic = any(_is_classic_box_label(cell) for cell in row)
        label_hit = any(_is_box_id_label(cell) for cell in row)
        fba_hits = sum(1 for cell in row[start:] if _fba_id_text(cell))
        named_hits = sum(1 for cell in row[start:] if _cell_box_no(cell) > 0)
        # 真箱唛优先。065ffde 起包装箱名称和箱号行同分，先出现的包装箱名称会抢走列，S-01 对不上。
        score = fba_hits * 100 + (10 if classic else 0) + (1 if label_hit else 0) + named_hits
        if score > best_score:
            best_score = score
            best_row = row
    return best_row if best_score > 0 else None


def _extract_box_data(
    rows: List[List[str]], header_idx: int, box_start: int, column_to_box: Dict[int, int]
) -> BoxData:
    box_data: BoxData = defaultdict(dict)
    if header_idx < 0:
        return {}

    for row in rows[header_idx + 1 :]:
        if not row:
            continue
        sku = str(row[0]).strip()
        if not sku or sku_key(sku) in {"sku", "seller sku"}:
            continue
        if re.search(r"(length|width|height|weight|长度|宽度|高度|重量|包装)", sku, flags=re.I):
            break

        for col_idx, true_box in column_to_box.items():
            if col_idx >= len(row):
                continue
            qty = _to_int(row[col_idx])
            if qty > 0:
                box_data[true_box][sku] = box_data[true_box].get(sku, 0) + qty

    return {k: dict(v) for k, v in sorted(box_data.items())}


def _fnsku_col_index(header_row: List[str]) -> int:
    for i, cell in enumerate(header_row):
        if str(cell or "").strip().upper() == "FNSKU":
            return i
    return -1


def _extract_sku_fnsku_map(rows: List[List[str]], header_idx: int) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if header_idx < 0 or header_idx >= len(rows):
        return out
    fn_col = _fnsku_col_index(rows[header_idx])
    if fn_col < 0:
        return out
    for row in rows[header_idx + 1 :]:
        if not row:
            continue
        sku = str(row[0]).strip()
        if not sku or sku_key(sku) in {"sku", "seller sku"}:
            continue
        if re.search(r"(length|width|height|weight|长度|宽度|高度|重量|包装)", sku, flags=re.I):
            break
        fnsku = str(row[fn_col]).strip().upper() if fn_col < len(row) else ""
        if sku and fnsku:
            out[sku] = fnsku
    return out


def _fba_id_text(cell: object) -> str:
    """只认 FBA…U 箱唛。P1 - B34 和没有 U 后缀的货件编号都不是箱号。"""
    from fba_tool.carton_math import is_fba_box_id

    text = normalize_fba_box_id(_norm_csv_cell(cell))
    return text if text and is_fba_box_id(text) else ""


def _extract_fba_box_ids(
    rows: List[List[str]], box_start: int, column_to_box: Dict[int, int]
) -> Dict[int, str]:
    """FBA 箱号只从真箱唛来。箱号列里的 P1 - B34 是箱名，写进 box_names。

    先认「箱号/编号」行上的 FBA…U（5457ff7 的口径）。后面的箱子名称、包装箱名称不能覆盖。
    这一行不是真箱唛时，再在同一箱子列里找；还没有，才按 U 后缀或从左到右对上。
    """
    del box_start
    found: Dict[int, str] = {}
    for row in rows:
        if not row or not any(_is_classic_box_label(cell) for cell in row):
            continue
        for col_idx, cell in enumerate(row):
            if col_idx not in column_to_box:
                continue
            token = _fba_id_text(cell)
            if token:
                found.setdefault(column_to_box[col_idx], token)
    loose: List[str] = []
    known = set(column_to_box.values())
    taken = set(found.values())
    for row in rows:
        for col_idx, cell in enumerate(row):
            token = _fba_id_text(cell)
            if not token or token in taken:
                continue
            if col_idx in column_to_box:
                box_no = column_to_box[col_idx]
                if box_no not in found:
                    found[box_no] = token
                    taken.add(token)
            elif token not in loose:
                loose.append(token)
    used = set(found.values())
    for token in loose:
        box_no = _fba_suffix_to_box_no(token)
        if box_no in known and box_no not in found and token not in used:
            found[box_no] = token
            used.add(token)
    missing_cols = [col for col in sorted(column_to_box) if column_to_box[col] not in found]
    leftover = [token for token in loose if token not in used]
    if leftover and len(leftover) == len(missing_cols):
        for col, token in zip(missing_cols, leftover):
            found[column_to_box[col]] = token
    return found


def _extract_box_names(rows: List[List[str]], column_to_box: Dict[int, int]) -> Dict[int, str]:
    """包装箱名称，以及箱号/箱子名称列里不是 FBA 箱唛的原文（第 13 批把箱名写在箱号列）。

    箱子名称可能写在箱号行前面。后面的真箱唛不能把已经记下的箱名擦掉。
    """
    names: Dict[int, str] = {}
    for col, text in _labeled_cells(rows, column_to_box, _is_packaging_name_label).items():
        if _fba_id_text(text):
            continue
        box_no = column_to_box.get(col)
        if box_no:
            names[box_no] = text
    sorted_cols = sorted(column_to_box)
    for row in rows:
        if not row or not sorted_cols or len(row) <= min(sorted_cols):
            continue
        if not _is_fba_mark_label(_row_packaging_label(row)):
            continue
        for col_idx in sorted_cols:
            box_no = column_to_box[col_idx]
            if box_no in names:
                continue
            cell = str(row[col_idx]).strip() if col_idx < len(row) else ""
            if not cell or cell.lower() == "nan" or _fba_id_text(cell):
                continue
            names[box_no] = cell
    return names


def _extract_box_specs(
    rows: List[List[str]], warehouse: str, box_start: int, column_to_box: Dict[int, int]
) -> List[Dict]:
    length_vals: Dict[int, float] = {}
    width_vals: Dict[int, float] = {}
    height_vals: Dict[int, float] = {}
    weight_vals: Dict[int, float] = {}
    length_unit = width_unit = height_unit = "in"
    weight_unit = "lb"
    fba_ids = _extract_fba_box_ids(rows, box_start, column_to_box)
    box_names = _extract_box_names(rows, column_to_box)

    sorted_cols = sorted(column_to_box.keys())

    for row in rows:
        if not row or not sorted_cols or len(row) <= min(sorted_cols):
            continue
        label = _row_packaging_label(row)
        label_lower = label.lower()

        if "包装箱长度" in label or ("length" in label_lower and "包装" in label_lower):
            length_vals = _row_values_by_col(row, sorted_cols)
            length_unit = detect_length_unit(label)
        elif "包装箱宽度" in label or ("width" in label_lower and "包装" in label_lower):
            width_vals = _row_values_by_col(row, sorted_cols)
            width_unit = detect_length_unit(label)
        elif "包装箱高度" in label or ("height" in label_lower and "包装" in label_lower):
            height_vals = _row_values_by_col(row, sorted_cols)
            height_unit = detect_length_unit(label)
        elif "包装箱重量" in label or ("weight" in label_lower and "包装" in label_lower):
            weight_vals = _row_values_by_col(row, sorted_cols)
            weight_unit = detect_weight_unit(label)

    records: List[Dict] = []
    for col_idx, true_box in column_to_box.items():
        l_raw = length_vals.get(col_idx, 0.0)
        w_raw = width_vals.get(col_idx, 0.0)
        h_raw = height_vals.get(col_idx, 0.0)
        wt_raw = weight_vals.get(col_idx, 0.0)
        if l_raw <= 0 and w_raw <= 0 and h_raw <= 0 and wt_raw <= 0:
            continue

        normalized = normalize_box_spec_row(
            l_raw, w_raw, h_raw, wt_raw,
            length_unit=length_unit, width_unit=width_unit,
            height_unit=height_unit, weight_unit=weight_unit,
        )
        if normalized["长(cm)"] <= 0 or normalized["宽(cm)"] <= 0 or normalized["高(cm)"] <= 0:
            continue
        if normalized["实重(kg)"] <= 0:
            continue

        declared_in = None
        declared_lb = None
        if str(length_unit).lower() in {"in", "inch", "inches", "英寸"}:
            declared_in = [l_raw, w_raw, h_raw]
        if str(weight_unit).lower() in {"lb", "lbs", "pound", "pounds", "磅"}:
            declared_lb = wt_raw
        records.append({
            "仓库代码": warehouse,
            "箱号": true_box,
            **normalized,
            "FBA箱号": fba_ids.get(true_box, ""),
            "箱名": box_names.get(true_box, ""),
            "declared_in": declared_in,
            "declared_lb": declared_lb,
        })
    return records


def _row_values_by_col(row: List[str], cols: List[int]) -> Dict[int, float]:
    return {col: _to_float(row[col]) if col < len(row) else 0.0 for col in cols}


def _records_to_box_data(records: List[Dict]) -> BoxData:
    box_data: BoxData = defaultdict(dict)
    for rec in records:
        box = int(rec["箱号"])
        sku = str(rec["SKU"])
        qty = int(rec["数量"])
        box_data[box][sku] = box_data[box].get(sku, 0) + qty
    return {k: dict(v) for k, v in sorted(box_data.items())}


def _box_data_to_items_df(
    box_data: BoxData,
    warehouse: str,
    sku_fnsku: Dict[str, str] | None = None,
) -> pd.DataFrame:
    fn_map = sku_fnsku or {}
    rows = []
    for box_no, skus in sorted(box_data.items()):
        for sku, qty in sorted(skus.items()):
            if qty > 0:
                rows.append(
                    {
                        "仓库代码": warehouse,
                        "箱号": box_no,
                        "SKU": sku,
                        "数量": qty,
                        "FNSKU": str(fn_map.get(sku, "") or "").strip().upper(),
                    }
                )
    if not rows:
        return pd.DataFrame(columns=["仓库代码", "箱号", "SKU", "数量", "FNSKU"])
    return pd.DataFrame(rows)


def _extract_fba_box_code(text: str) -> Tuple[str, int]:
    for token in re.findall(r"FBA[A-Z0-9]+U\d+", text.upper()):
        m = FBA_BOX_CODE_RE.match(token)
        if m:
            return m.group(1).upper(), int(m.group(2))
    return "", 0


def _fba_suffix_to_box_no(cell: str) -> int:
    m = FBA_BOX_CODE_RE.match(cell.upper())
    if m:
        return int(m.group(2))
    m2 = re.search(r"U0*(\d+)\s*$", cell.upper())
    return int(m2.group(1)) if m2 else 0


def join_wrapped_sku(text: str, known_skus: Optional[List[str]] = None) -> str:
    """Single SKU 下一行以 - 结尾时和后一行拼接，也能对上 CSV 里的 SKU。"""
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    capture = False
    parts: List[str] = []
    for ln in lines:
        upper = ln.upper()
        if "SINGLE SKU" in upper or upper.startswith("SKU"):
            capture = True
            parts = []
            continue
        if not capture:
            continue
        if re.search(r"(?:QTY|数量|P1\s*-)", ln, flags=re.I):
            break
        parts.append(ln.replace(" ", ""))
        joined = "".join(parts)
        if known_skus:
            for sku in known_skus:
                if joined.upper() == str(sku).upper():
                    return str(sku)
        if not ln.endswith("-"):
            break
    joined = "".join(parts)
    if joined.endswith("-FBA") or "PCS" in joined.upper():
        return joined
    flat = re.sub(r"\s+", "", text or "")
    match = re.search(r"(J-[A-Z0-9\-]+(?:\d+PCS-FBA))", flat, flags=re.I)
    return match.group(1) if match else ""


def _extract_pdf_sku(text: str) -> str:
    return join_wrapped_sku(text)


def _extract_pdf_qty(text: str) -> int:
    m = QTY_RE.search(text)
    if m:
        return int(m.group(1))
    m = re.search(r"数量\s*(\d+)", text)
    return int(m.group(1)) if m else 0


def _find_sku_header(rows: List[List[str]]) -> Tuple[int, int]:
    fallback: Tuple[int, int] | None = None
    for i, row in enumerate(rows):
        if not row:
            continue
        if sku_key(_norm_csv_cell(row[0])) != "sku":
            continue
        for j, cell in enumerate(row):
            if BOX_QTY_HEADER_RE.search(_norm_csv_cell(cell)):
                return i, j
        if fallback is None:
            fallback = (i, 7)
    if fallback is not None:
        return fallback
    return -1, 7


def _csv_meta(rows: List[List[str]], label: str) -> str:
    for row in rows[:20]:
        if not row:
            continue
        if str(row[0]).strip().strip('"') == label and len(row) > 1:
            return str(row[1]).strip().strip('"')
    return ""


def _warehouse_from_name(text: str) -> str:
    text = str(text or "").strip()
    m = WAREHOUSE_SUFFIX_RE.search(text)
    if m:
        cand = m.group(1).upper()
        if not cand.startswith("FBA") and cand not in WAREHOUSE_BLACKLIST:
            return cand

    for m in WAREHOUSE_STRICT_RE.finditer(text.upper()):
        cand = m.group(1)
        if cand.startswith("FBA") or cand in WAREHOUSE_BLACKLIST:
            continue
        if re.match(r"^[A-Z]{2,3}\d{1,2}$", cand) or re.match(r"^[A-Z]{4}$", cand):
            return cand
    return ""


def _is_known_warehouse(code: str) -> bool:
    from fba_tool.warehouse_codes import known_warehouse_codes

    return str(code or "").strip().upper() in known_warehouse_codes()


_ADDRESS_HINT_RE = re.compile(r"\b(?:RD|ROAD|ST|STREET|AVE|AVENUE|BLVD|DR|DRIVE|LN|LANE|PKWY|HWY)\b", re.I)
_STREET_NOISE = {"ROAD", "STREET", "AVENUE", "SUITE", "DRIVE", "LANE", "BLVD", "PARKWAY", "FLOOR", "UNIT", "CHARLOTTE"}


def _ignored_warehouse_tokens(text: str) -> List[str]:
    """不在白名单里的 4 字母片段只记调试日志，不写进仓码，也不进接口文案。"""
    ignored: List[str] = []
    for match in WAREHOUSE_STRICT_RE.finditer(str(text or "").upper()):
        cand = match.group(1)
        if len(cand) != 4 or not cand.isalpha() or cand in WAREHOUSE_BLACKLIST:
            continue
        if cand.startswith("FBA") or _is_known_warehouse(cand):
            continue
        if cand not in ignored:
            ignored.append(cand)
    if ignored:
        logger.debug("箱唛忽略非仓码 %s", ",".join(ignored))
    return ignored


def warehouse_from_label_text(text: str) -> Tuple[str, List[str]]:
    """箱唛仓码：先用已知仓码，再用地址库对地址行。街道名里的 4 个字母不当仓码。"""
    warnings: List[str] = []
    found: List[str] = []
    for match in WAREHOUSE_STRICT_RE.finditer(str(text or "").upper()):
        cand = match.group(1)
        if cand.startswith("FBA") or cand in WAREHOUSE_BLACKLIST:
            continue
        if _is_known_warehouse(cand):
            found.append(cand)
    if found:
        with_digit = [code for code in found if any(ch.isdigit() for ch in code)]
        return (with_digit[0] if with_digit else found[0]), warnings

    matched = _warehouse_from_address_library(text)
    if matched:
        return matched, warnings
    if _ADDRESS_HINT_RE.search(str(text or "")):
        warnings.append("箱唛地址没有匹配到仓库，未从街道名猜测仓码")
    return "", warnings


def _warehouse_from_address_library(text: str) -> str:
    """地址行里的门牌/街道能唯一对上地址库时，返回那个仓码。"""
    try:
        from fba_tool.warehouse_db import list_warehouses

        rows = list_warehouses("", limit=2000)
    except Exception:
        return ""
    text_u = str(text or "").upper()
    hits: List[str] = []
    for row in rows:
        addr = " ".join(str(row.get(key) or "") for key in ("address1", "address2", "city", "zip")).upper()
        tokens = [
            tok
            for tok in re.findall(r"[A-Z0-9]{4,}", addr)
            if tok not in _STREET_NOISE
        ]
        numbers = [tok for tok in tokens if any(ch.isdigit() for ch in tok)]
        names = [tok for tok in tokens if tok.isalpha() and len(tok) >= 4]
        if numbers and names and numbers[0] in text_u and any(name in text_u for name in names):
            hits.append(str(row.get("code") or "").upper())
    unique = [code for code in dict.fromkeys(hits) if code]
    return unique[0] if len(unique) == 1 else ""


def resolve_warehouse_with_warnings(
    csv_warehouse: str,
    pdf_name: str,
    pdf_pages: List[PdfBoxPage],
) -> Tuple[str, List[str]]:
    """只在已知仓码之间投票。街道碎片（如 DOWD）不能压过 CSV 上的仓码。"""
    warnings: List[str] = []
    ignored: set[str] = set()
    candidates: Dict[str, int] = {}
    pdf_text_cands: Dict[str, int] = {}
    for page in pdf_pages:
        cand = str(getattr(page, "warehouse_code", "") or "").strip().upper()
        if not cand:
            continue
        if not _is_known_warehouse(cand):
            if cand not in ignored:
                logger.debug("箱唛忽略非仓码 %s", cand)
                ignored.add(cand)
            continue
        pdf_text_cands[cand] = pdf_text_cands.get(cand, 0) + 1
    if pdf_text_cands:
        best_pdf = sorted(pdf_text_cands.items(), key=lambda item: item[1], reverse=True)[0][0]
        candidates[best_pdf] = candidates.get(best_pdf, 0) + 5

    csv_code = str(csv_warehouse or "").strip().upper()
    if csv_code and csv_code != "UNKN" and _is_known_warehouse(csv_code):
        candidates[csv_code] = candidates.get(csv_code, 0) + 4
    elif csv_code and csv_code != "UNKN":
        warnings.append(f"CSV 仓库代码 {csv_code} 不在已知仓库表里")

    pdf_file_cand = _warehouse_from_filename(pdf_name)
    if pdf_file_cand:
        candidates[pdf_file_cand] = candidates.get(pdf_file_cand, 0) + 3

    if not candidates:
        return "UNKN", warnings
    best = sorted(candidates.items(), key=lambda item: item[1], reverse=True)[0][0]
    return best, warnings


def resolve_optimal_warehouse(csv_warehouse: str, pdf_name: str, pdf_pages: List[PdfBoxPage]) -> str:
    """多源投票。未知的 4 字母街道碎片不参与。"""
    code, _warnings = resolve_warehouse_with_warnings(csv_warehouse, pdf_name, pdf_pages)
    return code


_UUID_RE = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}|\bwf[0-9a-fA-F-]{8,}", re.I)
_SCAN_SKIP_LABELS = ("工作流程名称", "工作流程编号", "工作流程 ID", "Workflow")


_FILE_WH_RE = re.compile(r"[A-Z]{3}[0-9][A-Z0-9]?")


def _warehouse_from_filename(file_name: str) -> str:
    """文件名里的仓库代码，例如“第一票ONT8.csv” → ONT8（中文与英文相邻也能识别）。

    文件名随手起，误判风险高（如“JAN5批次”“USA1”），所以只接受已知仓库表里的代码
    （内置白名单 + app_data/config/warehouse_codes.json），不按格式兜底。
    """
    from fba_tool.warehouse_codes import known_warehouse_codes

    import os

    stem = os.path.splitext(os.path.basename(str(file_name or "")))[0]
    for tok in re.findall(r"[A-Za-z0-9]+", stem):
        t = tok.upper()
        if _FILE_WH_RE.fullmatch(t) and t in known_warehouse_codes():
            return t
    return ""


def _scan_text(rows: List[List[str]]) -> str:
    """头部扫描文本：只看表头上方的“标签,值”元数据行；跳过工作流程 ID 行并去掉 UUID，
    避免把 UUID 片段（如 bf26）或列名（如 ASIN）误认成仓库代码。"""
    parts = []
    for r in rows[:12]:
        if not r or not any(str(c).strip() for c in r):
            break
        if any(str(r[0]).strip().strip('"').startswith(k) for k in _SCAN_SKIP_LABELS):
            continue
        parts.append(_UUID_RE.sub(" ", ",".join(r)))
    return " ".join(parts)


def _row_packaging_label(row: List[str]) -> str:
    for cell in row:
        text = str(cell or "").strip()
        if is_packaging_label(text):
            return text
    return str(row[0] if row else "").strip()


def _to_int(v) -> int:
    try:
        s = str(v).strip()
        if not s:
            return 0
        return int(float(s))
    except Exception:
        return 0


def _to_float(v) -> float:
    try:
        s = str(v).strip()
        if not s:
            return 0.0
        return float(s)
    except Exception:
        return 0.0
