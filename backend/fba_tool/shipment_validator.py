"""货件编号自动匹配 + CSV/PDF 三维交叉校验。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from fba_tool.box_label_filename import sort_pairs_by_box_label_pdf
from fba_tool.shipment_cross_check import run_cross_validation
from fba_tool.shipment_parser import (
    BoxData,
    CsvShipment,
    PdfBoxPage,
    PdfShipment,
    parse_csv_shipment,
    parse_pdf_pages,
    parse_pdf_shipment,
)


@dataclass
class ShipmentPair:
    shipment_id: str
    warehouse_code: str
    csv: CsvShipment
    pdf: PdfShipment
    pdf_name: str = ""


@dataclass
class UploadParseResult:
    csv_map: Dict[str, CsvShipment] = field(default_factory=dict)
    pdf_map: Dict[str, Tuple[str, PdfShipment]] = field(default_factory=dict)
    csv_bytes: Dict[str, bytes] = field(default_factory=dict)
    csv_names: Dict[str, str] = field(default_factory=dict)  # shipment_id -> 上传文件名
    pdf_bytes: Dict[str, bytes] = field(default_factory=dict)
    pdf_pages_map: Dict[str, List[PdfBoxPage]] = field(default_factory=dict)
    pdf_order: List[str] = field(default_factory=list)
    status_lines: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    ok: bool
    status_lines: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    pairs: List[ShipmentPair] = field(default_factory=list)
    all_box_items: pd.DataFrame = field(default_factory=pd.DataFrame)
    all_box_specs: pd.DataFrame = field(default_factory=pd.DataFrame)
    csv_bytes: Dict[str, bytes] = field(default_factory=dict)
    csv_names: Dict[str, str] = field(default_factory=dict)
    pdf_bytes: Dict[str, bytes] = field(default_factory=dict)
    cross_check_ok: bool = False
    worker_packing_rows: List[Dict[str, Any]] = field(default_factory=list)


ProgressFn = Callable[[str, int], None]


def parse_uploads(
    csv_files: List[Tuple[str, bytes]],
    pdf_files: List[Tuple[str, bytes]],
    *,
    on_progress: ProgressFn | None = None,
) -> UploadParseResult:
    csv_map: Dict[str, CsvShipment] = {}
    pdf_map: Dict[str, Tuple[str, PdfShipment]] = {}
    csv_bytes: Dict[str, bytes] = {}
    csv_names: Dict[str, str] = {}
    pdf_bytes: Dict[str, bytes] = {}
    pdf_pages_map: Dict[str, List[PdfBoxPage]] = {}
    status: List[str] = []
    errors: List[str] = []

    pdf_order: List[str] = []
    total_files = max(1, len(csv_files) + len(pdf_files))
    file_idx = 0

    for name, data in csv_files:
        file_idx += 1
        if on_progress:
            on_progress(
                f"解析 CSV：{name}",
                10 + int(22 * file_idx / total_files),
            )
        try:
            ship = parse_csv_shipment(data, file_name=name)
            if ship.shipment_id in csv_map:
                errors.append(f"❌ 重复上传：货件 CSV **{ship.shipment_id}** 传了不止一份（{name}），请删掉重复的文件再校验")
            csv_map[ship.shipment_id] = ship
            csv_bytes[ship.shipment_id] = data
            csv_names[ship.shipment_id] = name
            src = f"，来自{ship.warehouse_source}" if ship.warehouse_source else ""
            status.append(
                f"✅ 检测到 CSV: **{ship.shipment_id}** ➔ 自动识别仓库：**{ship.warehouse_code}**（{name}{src}）"
            )
        except Exception as exc:
            errors.append(f"❌ CSV 解析失败 [{name}]：{exc}")

    for name, data in pdf_files:
        file_idx += 1
        if on_progress:
            on_progress(
                f"解析 PDF 箱唛：{name}",
                10 + int(22 * file_idx / total_files),
            )
        try:
            ship = parse_pdf_shipment(data)
            pages = ship.pages or parse_pdf_pages(data)
            if ship.shipment_id in pdf_map:
                errors.append(f"❌ 重复上传：箱唛 PDF **{ship.shipment_id}** 传了不止一份（{name}），请删掉重复的文件再校验")
            pdf_map[ship.shipment_id] = (name, ship)
            pdf_bytes[ship.shipment_id] = data
            pdf_pages_map[ship.shipment_id] = pages
            if ship.shipment_id not in pdf_order:
                pdf_order.append(ship.shipment_id)
            status.append(
                f"✅ 检测到 PDF 箱唛: **{ship.shipment_id}**（共 {ship.page_count} 页 · {name}）"
            )
        except Exception as exc:
            errors.append(f"❌ PDF 解析失败 [{name}]：{exc}")

    for sid, csv_ship in csv_map.items():
        if sid not in pdf_map:
            errors.append(f"⚠️ CSV **{sid}**（{csv_ship.warehouse_code}）未找到货件编号匹配的 PDF")

    for sid in pdf_map:
        if sid not in csv_map:
            errors.append(f"⚠️ PDF **{sid}** 未找到货件编号匹配的 CSV")

    if on_progress:
        on_progress("CSV / PDF 解析完成，正在检查货件配对…", 35)

    return UploadParseResult(
        csv_map=csv_map,
        pdf_map=pdf_map,
        csv_bytes=csv_bytes,
        csv_names=csv_names,
        pdf_bytes=pdf_bytes,
        pdf_pages_map=pdf_pages_map,
        pdf_order=pdf_order,
        status_lines=status,
        errors=errors,
    )


def preview_auto_mapping(
    csv_files: List[Tuple[str, bytes]],
    pdf_files: List[Tuple[str, bytes]],
) -> Tuple[List[str], List[str]]:
    parsed = parse_uploads(csv_files, pdf_files)
    return parsed.status_lines, parsed.errors


def validate_shipments(
    csv_files: List[Tuple[str, bytes]],
    pdf_files: List[Tuple[str, bytes]],
    parsed: UploadParseResult | None = None,
    *,
    step1_rows: Optional[List[Dict[str, Any]]] = None,
    on_progress: ProgressFn | None = None,
) -> ValidationResult:
    if parsed is None:
        parsed = parse_uploads(csv_files, pdf_files, on_progress=on_progress)
    csv_map = parsed.csv_map
    pdf_map = parsed.pdf_map
    status = list(parsed.status_lines)
    errors = list(parsed.errors)

    pairs: List[ShipmentPair] = []
    all_items: List[pd.DataFrame] = []
    all_specs: List[pd.DataFrame] = []

    order = list(parsed.pdf_order) if parsed.pdf_order else list(csv_map.keys())
    seen: set[str] = set()
    
    from fba_tool.shipment_parser import resolve_optimal_warehouse

    for sid in order:
        csv_ship = csv_map.get(sid)
        pdf_entry = pdf_map.get(sid)
        if not csv_ship or not pdf_entry:
            continue
        pdf_name, pdf_ship = pdf_entry
        
        pdf_pages = parsed.pdf_pages_map.get(sid, [])
        best_wh = resolve_optimal_warehouse(csv_ship.warehouse_code, pdf_name, pdf_pages)
        if best_wh != "UNKN" and best_wh != csv_ship.warehouse_code:
            status.append(f"🔧 智能修正：货件 **{sid}** 仓库从 [{csv_ship.warehouse_code}] 修正为 ➔ **{best_wh}**")
            csv_ship.warehouse_code = best_wh
            
        pairs.append(ShipmentPair(sid, csv_ship.warehouse_code, csv_ship, pdf_ship, pdf_name))
        seen.add(sid)
        items = csv_ship.box_items.copy()
        specs = csv_ship.box_specs.copy()
        if not items.empty:
            items["仓库代码"] = csv_ship.warehouse_code
        if not specs.empty:
            specs["仓库代码"] = csv_ship.warehouse_code
        all_items.append(items)
        all_specs.append(specs)

    for sid, csv_ship in csv_map.items():
        if sid in seen:
            continue
        pdf_entry = pdf_map.get(sid)
        if not pdf_entry:
            continue
        pdf_name, pdf_ship = pdf_entry
        
        pdf_pages = parsed.pdf_pages_map.get(sid, [])
        best_wh = resolve_optimal_warehouse(csv_ship.warehouse_code, pdf_name, pdf_pages)
        if best_wh != "UNKN" and best_wh != csv_ship.warehouse_code:
            status.append(f"🔧 智能修正：货件 **{sid}** 仓库从 [{csv_ship.warehouse_code}] 修正为 ➔ **{best_wh}**")
            csv_ship.warehouse_code = best_wh
            
        pairs.append(ShipmentPair(sid, csv_ship.warehouse_code, csv_ship, pdf_ship, pdf_name))
        seen.add(sid)
        items = csv_ship.box_items.copy()
        specs = csv_ship.box_specs.copy()
        if not items.empty:
            items["仓库代码"] = csv_ship.warehouse_code
        if not specs.empty:
            specs["仓库代码"] = csv_ship.warehouse_code
        all_items.append(items)
        all_specs.append(specs)

    pairs = sort_pairs_by_box_label_pdf(pairs)
    if on_progress:
        on_progress(f"已匹配 {len(pairs)} 个货件，开始三维交叉校验…", 42)

    cross = run_cross_validation(
        pairs,
        parsed.pdf_pages_map,
        step1_rows=step1_rows,
        on_progress=on_progress,
    )
    status.extend(cross.status_lines)
    compare_errors = cross.errors

    hard_errors = [e for e in compare_errors if e.startswith("❌")]
    # S8 D12：同一货件重复上传是硬错误（以前只警告、ok=True，可能导致重复计数）
    dup_errors = [e for e in errors if e.startswith("❌ 重复上传")]
    ok = len(hard_errors) == 0 and not dup_errors and len(pairs) > 0 and len(csv_map) == len(pdf_map)

    all_errors = errors + compare_errors

    return ValidationResult(
        ok=ok,
        status_lines=status,
        errors=all_errors,
        pairs=pairs,
        all_box_items=pd.concat(all_items, ignore_index=True) if all_items else pd.DataFrame(),
        all_box_specs=pd.concat(all_specs, ignore_index=True) if all_specs else pd.DataFrame(),
        csv_bytes=parsed.csv_bytes,
        csv_names=parsed.csv_names,
        pdf_bytes=parsed.pdf_bytes,
        cross_check_ok=cross.ok,
        worker_packing_rows=cross.worker_packing_rows,
    )


def compare_box_data(
    csv_data: BoxData,
    pdf_data: BoxData,
    warehouse: str,
    shipment_id: str,
) -> List[str]:
    """兼容旧接口 — 简单逐 SKU 比对。"""
    errors: List[str] = []
    if not csv_data:
        errors.append(f"❌ [{warehouse}] 货件 {shipment_id}：CSV 未解析到有效箱内 SKU 数据。")
        return errors
    if not pdf_data:
        errors.append(f"❌ [{warehouse}] 货件 {shipment_id}：PDF 未解析到有效箱唛数据。")
        return errors

    all_boxes = sorted(set(csv_data.keys()) | set(pdf_data.keys()))
    for box_no in all_boxes:
        csv_skus = csv_data.get(box_no, {})
        pdf_skus = pdf_data.get(box_no, {})
        all_skus = sorted(set(csv_skus.keys()) | set(pdf_skus.keys()))
        for sku in all_skus:
            csv_qty = csv_skus.get(sku, 0)
            pdf_qty = pdf_skus.get(sku, 0)
            if csv_qty != pdf_qty:
                errors.append(
                    f"❌ [{warehouse}] 错误：第 {box_no} 箱 SKU: {sku}，CSV显示为 {csv_qty}，PDF显示为 {pdf_qty}。"
                )
    return errors


def cross_validate_box_data(csv_box_items: pd.DataFrame, pdf_items: pd.DataFrame) -> Tuple[bool, List[str]]:
    """兼容旧接口。"""
    csv_data = _items_df_to_box_data(csv_box_items)
    pdf_data = _items_df_to_box_data(pdf_items)
    wh = str(csv_box_items["仓库代码"].iloc[0]) if not csv_box_items.empty else "UNKN"
    errors = compare_box_data(csv_data, pdf_data, wh, "")
    return len(errors) == 0, errors


def _items_df_to_box_data(df: pd.DataFrame) -> BoxData:
    if df.empty:
        return {}
    grouped = df.groupby(["箱号", "SKU"], as_index=False)["数量"].sum()
    box_data: BoxData = {}
    for _, row in grouped.iterrows():
        box = int(row["箱号"])
        sku = str(row["SKU"])
        box_data.setdefault(box, {})[sku] = int(row["数量"])
    return box_data
