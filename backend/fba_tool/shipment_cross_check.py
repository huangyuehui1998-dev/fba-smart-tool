"""CSV ↔ PDF 三维深度交叉校验 + Step 1 宏观兜底 + 工人装箱单数据构建。"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import re

from fba_tool.shipment_parser import (
    CsvShipment,
    PdfBoxPage,
    format_box_u_label,
    join_wrapped_sku,
    normalize_fba_box_id,
    snapshot_box_id,
)

MIXED_SKU_RE = re.compile(r"mixed\s*sku", re.I)


@dataclass
class CrossCheckResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    status_lines: List[str] = field(default_factory=list)
    worker_packing_rows: List[Dict[str, Any]] = field(default_factory=list)


def _norm_sku(s: str) -> str:
    """S9-step3：统一用 sku_keys.sku_key（NFKC + casefold），这里另外去掉中间空白（原有行为）。"""
    from fba_tool.sku_keys import sku_key

    return re.sub(r"\s+", "", sku_key(s))


def _box_label(fba_id: str, box_no: int) -> str:
    if fba_id:
        m = re.search(r"U0*(\d+)\s*$", fba_id.upper())
        if m:
            return f"U{int(m.group(1)):03d}"
        return fba_id
    return format_box_u_label(box_no)


def _csv_boxes_with_fba(csv: CsvShipment) -> Dict[int, str]:
    ids = dict(csv.box_fba_ids)
    for box_no in csv.box_data:
        ids.setdefault(box_no, "")
    return ids


def _u_token(fba_id: str, box_no: int) -> str:
    """保留箱号里的 U 后缀原样（U000001），供重复箱唛提示引用。"""
    match = re.search(r"(U\d+)\s*$", str(fba_id or "").upper())
    if match:
        return match.group(1)
    return _box_label(fba_id, box_no)


def _is_soft_finding(message: str) -> bool:
    return str(message or "").lstrip().startswith("⚠️")


def _pdf_pages_grouped(pages: List[PdfBoxPage]) -> Dict[str, List[PdfBoxPage]]:
    groups: Dict[str, List[PdfBoxPage]] = defaultdict(list)
    for page in pages:
        key = normalize_fba_box_id(page.fba_box_id)
        if key:
            groups[key].append(page)
    return groups


def validate_step1_macro_totals(
    pairs: List[Any],
    step1_rows: List[Dict[str, Any]],
) -> List[str]:
    """④ 宏观兜底：CSV 全货件 SKU 数量总和须与 Step 1 发货总数一致。"""
    errors: List[str] = []
    if not step1_rows:
        return errors

    expected_by_sku: Dict[str, int] = defaultdict(int)
    shown: Dict[str, str] = {}  # 规范键 → 原始写法（提示里显示原始写法）
    expected_total = 0
    for row in step1_rows:
        sku = str(row.get("SKU简称") or row.get("SKU") or "").strip()
        qty = _to_int(row.get("发货总数"))
        if sku and qty > 0:
            expected_by_sku[_norm_sku(sku)] += qty
            shown.setdefault(_norm_sku(sku), sku)
            expected_total += qty

    actual_by_sku: Dict[str, int] = defaultdict(int)
    actual_total = 0
    for pair in pairs:
        for box_skus in pair.csv.box_data.values():
            for sku, qty in box_skus.items():
                if qty > 0:
                    actual_by_sku[_norm_sku(sku)] += int(qty)
                    shown.setdefault(_norm_sku(sku), str(sku).strip())
                    actual_total += int(qty)

    if expected_total <= 0:
        return errors

    if actual_total != expected_total:
        errors.append(
            f"❌ 【宏观数量不符】CSV 全部货件合计 {actual_total} 件，"
            f"Step 1 录入发货总数 {expected_total} 件。"
            f"（请返回 Step 1 核对发货总数，或确认上传的 CSV 是否为最新版）"
        )

    # 逐 SKU 比对：即使总数相同，也要防止「A 少发、B 多发」的相互抵消错误。
    all_skus = set(expected_by_sku) | set(actual_by_sku)
    for sku_key in sorted(all_skus):
        exp = expected_by_sku.get(sku_key, 0)
        act = actual_by_sku.get(sku_key, 0)
        if exp == act:
            continue
        name = shown.get(sku_key, sku_key)
        if exp == 0:
            errors.append(
                f"❌ 【SKU 多发/未录入】CSV 中 SKU {name} 合计 {act} 件，"
                f"但 Step 1 未录入该 SKU。（请确认 SKU 简称是否与亚马逊 Merchant SKU 一致）"
            )
        elif act == 0:
            errors.append(
                f"❌ 【SKU 漏发】Step 1 录入 SKU {name} 共 {exp} 件，"
                f"但 CSV 全部货件中未找到该 SKU。（请确认是否漏装，或 SKU 简称与亚马逊命名不一致）"
            )
        else:
            errors.append(
                f"❌ 【SKU 数量不符】SKU {name}：CSV 合计 {act} 件，"
                f"Step 1 录入 {exp} 件，差 {act - exp:+d} 件。（请核对该 SKU 的发货数量）"
            )

    return errors


def cross_validate_pair(
    csv: CsvShipment,
    pdf_pages: List[PdfBoxPage],
    warehouse: str,
    shipment_id: str,
) -> List[str]:
    """①–③ 逐箱 CSV ↔ PDF 三维校验。"""
    errors: List[str] = []
    if not csv.box_data:
        errors.append(f"❌ [{warehouse}] 货件 {shipment_id}：CSV 未解析到有效箱内 SKU 数据。")
        return errors
    if not pdf_pages:
        errors.append(f"❌ [{warehouse}] 货件 {shipment_id}：PDF 未解析到有效箱唛页面。")
        return errors

    fba_by_box = _csv_boxes_with_fba(csv)
    grouped_pages = _pdf_pages_grouped(pdf_pages)
    for key, group in grouped_pages.items():
        if len(group) < 2:
            continue
        token = _u_token(group[0].fba_box_id, group[0].box_no)
        errors.append(f"❌ 【重复箱唛】箱号 {token} 出现 {len(group)} 页")
    pdf_by_fba = {key: group[0] for key, group in grouped_pages.items()}

    csv_box_nos = sorted(csv.box_data.keys())
    csv_fba_ids = [
        normalize_fba_box_id(fba_by_box.get(b, "")) for b in csv_box_nos if fba_by_box.get(b, "")
    ]

    pdf_with_id = [p for p in pdf_pages if normalize_fba_box_id(p.fba_box_id)]
    seen_fba: Dict[str, int] = {}
    for page in pdf_with_id:
        key = normalize_fba_box_id(page.fba_box_id)
        seen_fba[key] = seen_fba.get(key, 0) + 1
    for key, count in seen_fba.items():
        if count > 1:
            errors.append(f"❌ 【重复箱唛】箱号 {key} 在 PDF 中出现了 {count} 次。")
    if len(pdf_with_id) != len(csv_box_nos):
        errors.append(
            f"❌ 【箱数不一致】[{warehouse}] 货件 {shipment_id}：CSV 共 {len(csv_box_nos)} 箱，"
            f"PDF 有效箱唛页 {len(pdf_with_id)} 页。"
        )

    unlabeled = 0
    for box_no in csv_box_nos:
        fba_raw = fba_by_box.get(box_no, "")
        fba_key = normalize_fba_box_id(fba_raw)
        label = _box_label(fba_raw, box_no)
        csv_skus = csv.box_data.get(box_no, {})

        if not fba_key:
            errors.append(
                f"❌ 【箱号缺失】[{warehouse}] 第 {box_no} 箱 CSV 未找到 Amazon Box ID。"
                f"（请确认 CSV 为亚马逊后台导出的最新装箱单，且含 FBA...U 箱号列）"
            )
            continue

        pdf_page = pdf_by_fba.get(fba_key)
        if not pdf_page:
            errors.append(
                f"❌ 【箱号缺失】CSV 要求装箱 {label}（{fba_raw}），"
                f"但上传的 PDF 箱唛中未找到该单号。"
                f"（请确认已上传该货件对应的箱唛 PDF，且与 CSV 为同一批次）"
            )
            continue

        sku_count = len([q for q in csv_skus.values() if q > 0])
        if sku_count <= 0:
            continue

        if sku_count == 1 and pdf_page.is_mixed:
            errors.append(
                f"❌ 【混装标签异常】箱号 {label} 为单 SKU 箱，箱唛却标注 Mixed SKUs。"
                f"（请确认该箱是否混装；单 SKU 箱不得使用 Mixed 箱唛）"
            )
            continue

        if sku_count > 1 and (
            pdf_page.is_mixed or MIXED_SKU_RE.search(str(pdf_page.raw_text or ""))
        ):
            continue

        pdf_sku = str(pdf_page.sku or "").strip()
        if not pdf_sku:
            pdf_sku = join_wrapped_sku(pdf_page.raw_text or "", list(csv_skus))
        try:
            pdf_qty = int(pdf_page.qty or 0)
        except (TypeError, ValueError):
            pdf_qty = 0
        fnsku = str(pdf_page.fnsku or "").strip().upper()
        csv_fnskus = {str(value).strip().upper() for value in (csv.sku_fnsku or {}).values() if str(value).strip()}
        if not pdf_sku:
            recognized_fnsku = bool(fnsku) and (not csv_fnskus or fnsku in csv_fnskus)
            recognized_qty = pdf_qty > 0 and (
                sku_count != 1 or pdf_qty == int(next(iter(csv_skus.values())))
            )
            if not pdf_sku and not fnsku and pdf_qty <= 0:
                errors.append(f"❌ 【箱唛未识别】箱号 {label} 的 SKU、FNSKU、数量都识别不出")
            elif recognized_fnsku or recognized_qty:
                errors.append(f"⚠️ 箱号 {label} 箱唛 SKU 未识别，已按 FNSKU/数量核对")
            else:
                errors.append(f"❌ 【箱唛未识别】箱号 {label} 的 SKU、FNSKU、数量都对不上")
            continue

        if sku_count == 1:
            csv_sku = next(iter(csv_skus.keys()))
            csv_qty = int(csv_skus[csv_sku])
            if _norm_sku(pdf_sku) != _norm_sku(csv_sku):
                errors.append(
                    f"❌ 【产品不符】箱号 {label} 的 PDF 标签 SKU 为 {pdf_sku}，"
                    f"但 CSV 要求装 {csv_sku}。"
                    f"（若两者其实是同一产品，请统一 SKU 简称与亚马逊 Merchant SKU 命名后重试）"
                )
            if pdf_qty != csv_qty:
                errors.append(
                    f"❌ 【数量冲突】箱号 {label} 的 PDF 标签显示数量为 {pdf_qty}，"
                    f"但 CSV 数据库中要求装 {csv_qty}。"
                    f"（请核对该箱实际装箱数量，并确认 CSV 与箱唛 PDF 为同一次货件生成）"
                )
        elif pdf_sku and _norm_sku(pdf_sku) not in {_norm_sku(s) for s in csv_skus}:
            errors.append(
                f"❌ 【混装产品异常】箱号 {label} CSV 为混装 {sku_count} SKU，"
                f"PDF 却标注单一 SKU {pdf_sku} 且非 Mixed SKUs。"
                f"（请确认该箱是否为混装箱；若是，箱唛应标注 Mixed SKUs）"
            )

    if unlabeled:
        errors.append(
            f"⚠️ [{warehouse}] 货件 {shipment_id}：本票 {unlabeled} 箱箱唛无 SKU/数量文本，"
            f"已跳过逐箱 SKU 比对（箱号、箱数比对照常）"
        )

    for page in pdf_with_id:
        key = normalize_fba_box_id(page.fba_box_id)
        if key and key not in csv_fba_ids:
            label = _box_label(page.fba_box_id, page.box_no)
            errors.append(
                f"❌ 【多余箱唛】PDF 存在箱号 {label}（{page.fba_box_id}），"
                f"但 CSV 中无对应装箱要求。"
                f"（请确认是否多打了箱唛，或漏传了对应的 CSV 装箱单）"
            )

    return errors


def run_cross_validation(
    pairs: List[Any],
    pdf_pages_map: Dict[str, List[PdfBoxPage]],
    step1_rows: Optional[List[Dict[str, Any]]] = None,
    *,
    on_progress: Callable[[str, int], None] | None = None,
) -> CrossCheckResult:
    result = CrossCheckResult(ok=True)
    result.status_lines.append("⏳ 正在与物理箱唛进行三维交叉比对...")
    if on_progress:
        on_progress("正在三维交叉校验 CSV ↔ PDF 箱唛…", 48)

    compare_errors: List[str] = []
    total = max(1, len(pairs))
    for i, pair in enumerate(pairs):
        if on_progress:
            on_progress(
                f"校验 [{pair.warehouse_code}] {pair.shipment_id}（{i + 1}/{len(pairs)}）",
                48 + int(32 * (i + 1) / total),
            )
        pages = pdf_pages_map.get(pair.shipment_id, [])
        pair_messages = cross_validate_pair(
            pair.csv, pages, pair.warehouse_code, pair.shipment_id
        )
        pair_errors = [msg for msg in pair_messages if not _is_soft_finding(msg)]
        pair_warnings = [msg for msg in pair_messages if _is_soft_finding(msg)]
        compare_errors.extend(pair_errors)
        result.warnings.extend(pair_warnings)
        result.status_lines.extend(pair_warnings)
        if not pair_errors:
            box_n = pair.csv.box_count or len(pair.csv.box_data)
            result.status_lines.append(
                f"✅ [{pair.warehouse_code}] {pair.shipment_id}：{box_n} 箱三维交叉校验通过"
            )

    if step1_rows:
        if on_progress:
            on_progress("正在核对 Step 1 发货总数（宏观兜底）…", 82)
        compare_errors.extend(validate_step1_macro_totals(pairs, step1_rows))

    result.errors = compare_errors
    result.ok = len(compare_errors) == 0 and len(pairs) > 0

    if result.ok:
        if on_progress:
            on_progress("交叉校验通过，正在生成工人装箱单数据…", 84)
        result.worker_packing_rows = build_worker_packing_rows(pairs)
        result.status_lines.append("✅ 交叉校验通过，装箱单数据已就绪。")
    else:
        result.status_lines.append(f"❌ 校验未通过，共 {len(compare_errors)} 项")

    return result


# 申报箱重/箱规与本地方案的可接受偏差
DECLARED_WEIGHT_TOLERANCE = 0.10
DECLARED_VOLUME_TOLERANCE = 0.10


def _declared_specs_by_box(pairs: List[Any]) -> Dict[Tuple[str, int], Dict[str, Any]]:
    out: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for pair in pairs:
        specs = getattr(pair.csv, "box_specs", None)
        if specs is None or getattr(specs, "empty", True):
            continue
        for _, row in specs.iterrows():
            try:
                box_no = int(row["箱号"])
            except (TypeError, ValueError, KeyError):
                continue
            length = float(row.get("长(cm)") or 0)
            width = float(row.get("宽(cm)") or 0)
            height = float(row.get("高(cm)") or 0)
            ids = getattr(pair.csv, "box_fba_ids", {}) or {}
            out[(pair.shipment_id, box_no)] = {
                "warehouse": pair.warehouse_code,
                "fba_box_id": snapshot_box_id(row, ids),
                "weight_kg": float(row.get("实重(kg)") or 0),
                "volume_cm3": length * width * height,
                "length_cm": length,
                "width_cm": width,
                "height_cm": height,
            }
    return out


def _deviation(declared: float, planned: float) -> Optional[float]:
    if planned <= 0 or declared <= 0:
        return None
    return abs(declared - planned) / planned


def check_declared_box_specs(
    pairs: List[Any],
    local_metrics: Any,
    matches: Optional[List[Any]] = None,
    *,
    weight_tolerance: float = DECLARED_WEIGHT_TOLERANCE,
    volume_tolerance: float = DECLARED_VOLUME_TOLERANCE,
) -> Dict[str, Any]:
    """比对申报给亚马逊的箱重/箱规与 Step 2 本地排箱方案。

    CSV 里的 box_specs 是你申报出去的值，亚马逊入库会复磅复尺，不符即产生
    重量差异费与尺寸调整费。三维交叉校验只看箱号/SKU/数量，从不碰这两个字段。
    结果为软告警，不阻断校验。
    """
    out: Dict[str, Any] = {"ok": True, "warnings": [], "rows": [], "compared_boxes": 0}
    declared = _declared_specs_by_box(pairs)
    if not declared:
        return out

    planned: Dict[int, Dict[str, float]] = {}
    if local_metrics is not None and not getattr(local_metrics, "empty", True):
        for _, row in local_metrics.iterrows():
            planned[int(row["箱号"])] = {
                "gross_kg": float(row.get("毛重(kg)") or 0),
                "volume_cm3": float(row.get("体积(cm3)") or 0),
            }

    for match in matches or []:
        spec = declared.get((match.shipment_id, match.amazon_box_no))
        plan = planned.get(match.local_box_no)
        if not spec or not plan:
            continue
        out["compared_boxes"] += 1
        label = spec["fba_box_id"] or match.local_box_label

        weight_dev = _deviation(spec["weight_kg"], plan["gross_kg"])
        if weight_dev is not None and weight_dev > weight_tolerance:
            out["rows"].append(
                {
                    "kind": "weight",
                    "box": label,
                    "declared": round(spec["weight_kg"], 3),
                    "planned": round(plan["gross_kg"], 3),
                    "deviation_pct": round(weight_dev * 100, 1),
                }
            )
            out["warnings"].append(
                f"⚠️ 【申报箱重不符】箱 {label} 向亚马逊申报 {spec['weight_kg']:g} kg，"
                f"Step 2 方案测算为 {plan['gross_kg']:g} kg，偏差 {weight_dev * 100:.1f}%。"
                f"（复磅不符会产生重量差异费，请确认申报值）"
            )

        volume_dev = _deviation(spec["volume_cm3"], plan["volume_cm3"])
        if volume_dev is not None and volume_dev > volume_tolerance:
            out["rows"].append(
                {
                    "kind": "volume",
                    "box": label,
                    "declared": round(spec["volume_cm3"] / 1000, 2),
                    "planned": round(plan["volume_cm3"] / 1000, 2),
                    "deviation_pct": round(volume_dev * 100, 1),
                }
            )
            out["warnings"].append(
                f"⚠️ 【申报箱规不符】箱 {label} 向亚马逊申报 "
                f"{spec['length_cm']:g}×{spec['width_cm']:g}×{spec['height_cm']:g} cm，"
                f"与 Step 2 方案体积相差 {volume_dev * 100:.1f}%。"
                f"（尺寸申报不符会触发尺寸调整费）"
            )

    # 宏观兜底：即使建立不了逐箱映射（亚马逊主导模式常见），总量偏差也要暴露
    total_declared = sum(s["weight_kg"] for s in declared.values())
    total_planned = sum(p["gross_kg"] for p in planned.values())
    total_dev = _deviation(total_declared, total_planned)
    if total_dev is not None and total_dev > weight_tolerance:
        out["rows"].append(
            {
                "kind": "total_weight",
                "box": "合计",
                "declared": round(total_declared, 2),
                "planned": round(total_planned, 2),
                "deviation_pct": round(total_dev * 100, 1),
            }
        )
        out["warnings"].append(
            f"⚠️ 【申报总重不符】全部货件向亚马逊申报合计 {total_declared:.2f} kg，"
            f"Step 2 方案测算合计 {total_planned:.2f} kg，偏差 {total_dev * 100:.1f}%。"
            f"（请核对是否用了错误的称重数据）"
        )

    out["ok"] = not out["warnings"]
    return out


def build_worker_packing_rows(pairs: List[Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    by_wh: Dict[str, List[ShipmentPair]] = defaultdict(list)
    for pair in pairs:
        by_wh[pair.warehouse_code].append(pair)

    for wh in sorted(by_wh.keys()):
        rows.append(
            {
                "row_type": "warehouse_header",
                "仓库代码": wh,
                "亚马逊箱号": "",
                "Merchant SKU": "",
                "装箱数量": "",
                "工人确认": "",
            }
        )
        wh_pairs = by_wh[wh]
        boxes: List[Tuple[str, int, str, Dict[str, int]]] = []
        for pair in wh_pairs:
            fba_map = _csv_boxes_with_fba(pair.csv)
            for box_no in sorted(pair.csv.box_data.keys()):
                fba_id = fba_map.get(box_no) or format_box_u_label(box_no)
                boxes.append((wh, box_no, fba_id, pair.csv.box_data[box_no]))

        boxes.sort(key=lambda x: (x[0], normalize_fba_box_id(x[2]) or str(x[1]).zfill(6)))

        for _, box_no, fba_id, skus in boxes:
            rows.append(
                {
                    "row_type": "box_header",
                    "仓库代码": wh,
                    "亚马逊箱号": fba_id,
                    "Merchant SKU": "",
                    "装箱数量": "",
                    "工人确认": "[   ]",
                }
            )
            for sku, qty in sorted(skus.items()):
                if qty <= 0:
                    continue
                rows.append(
                    {
                        "row_type": "item",
                        "仓库代码": wh,
                        "亚马逊箱号": "",
                        "Merchant SKU": sku,
                        "装箱数量": int(qty),
                        "工人确认": "[   ]",
                    }
                )
    return rows


def _to_int(val: Any) -> int:
    try:
        return int(float(str(val).replace(",", "").strip() or 0))
    except (TypeError, ValueError):
        return 0
