"""箱侧冒烟的独立复算。只读原始文件，不导入产品代码。

进位 = 账单 − Σ(单箱计费重)。推算账单是否等于「合计 ↑0.5」另算，不拿来代替进位。
第 15 批账单与逐箱合计的差额、以及 pending_verification，都不在这里给出红绿结论。
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path
from typing import Any


class LayoutMissing(FileNotFoundError):
    """目录在，但缺第 13/14/15 批复算要用的文件。这是失败，不是跳过。"""


def realdata_root() -> Path:
    return Path(os.environ.get("FBA_REALDATA_DIR", "/workspace/fba_tool/realdata"))


def available() -> bool:
    root = realdata_root()
    if not root.is_dir():
        return False
    return any(root.iterdir())


def policy_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "policy.default.json"


_FBA_BOX = re.compile(r"^FBA[0-9A-Z]+U[0-9]+$", re.IGNORECASE)
_BATCH_DIR = re.compile(r"(?:^|[/\\])batches[/\\](\d+)(?:[/\\]|$)", re.IGNORECASE)
_STA_N = {"13": 2, "14": 6, "15": 1}
_LABELS = ("包装箱名称", "包装箱重量", "包装箱宽度", "包装箱长度", "包装箱高度", "箱号")
_INCH = Decimal("2.54")
_LB = Decimal("0.45359237")
_DIVISOR = Decimal("6000")


def D(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(str(value).strip())


def q(value: Any, places: int) -> Decimal:
    quantum = Decimal("1").scaleb(-places)
    return D(value).quantize(quantum, rounding=ROUND_HALF_UP)


def volumetric(length: Any, width: Any, height: Any) -> Decimal:
    return q(D(length) * D(width) * D(height) / _DIVISOR, 2)


def chargeable(weight: Any, dims: list[Any] | None) -> Decimal:
    actual = q(weight, 3)
    if not dims or not any(D(item) > 0 for item in dims):
        return actual
    return max(actual, volumetric(dims[0], dims[1], dims[2]))


def round_up_half_kg(total: Any) -> Decimal:
    value = D(total)
    if value <= 0:
        return Decimal("0.0")
    units = (value / Decimal("0.5")).to_integral_value(rounding=ROUND_CEILING)
    return q(units * Decimal("0.5"), 1)


def _compact(value: Any) -> str:
    return str(value or "").replace("：", "").replace(":", "").replace(" ", "").replace("\u3000", "").strip()


def _batch_of(path: Path) -> str:
    text = str(path)
    found = re.search(r"第\s*(\d+)\s*批", text)
    if found:
        return found.group(1)
    found = _BATCH_DIR.search(text)
    if found:
        return found.group(1)
    return ""


def _files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or path.name.startswith("~$"):
            continue
        if path.suffix.lower() not in {".xlsx", ".xlsm", ".csv"}:
            continue
        yield path


def _grid(path: Path) -> list[list[Any]]:
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb.worksheets[0]
        return [list(row) for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def _sheets(path: Path) -> list[tuple[str, list[list[Any]]]]:
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        return [(ws.title, [list(row) for row in ws.iter_rows(values_only=True)]) for ws in wb.worksheets]
    finally:
        wb.close()


def _text_id(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _num(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return D(value)
    except Exception:
        return None


def _header_at(headers: list[str], names: list[str]) -> int | None:
    for name in names:
        if name in headers:
            return headers.index(name)
    return None


def _cell(row: list[Any], index: int | None) -> Any:
    if index is None or index >= len(row):
        return None
    return row[index]


def parse_measure_grid(grid: list[list[Any]]) -> dict[str, Any]:
    """九方逐箱表。表头有入库计费重时按扁平行读，否则认表尾标签。"""
    header_at = None
    headers: list[str] = []
    for index, row in enumerate(grid):
        headers = [str(cell or "").strip() for cell in row]
        if "外箱号" in headers or "FBA箱号" in headers:
            header_at = index
            break
    if header_at is None:
        return {"boxes": [], "bills": {}}
    box_at = _header_at(headers, ["外箱号", "FBA箱号", "箱号"])
    weight_at = _header_at(headers, ["单箱实重", "实重", "实重(kg)", "重量"])
    length_at = _header_at(headers, ["长", "长(cm)", "长度"])
    width_at = _header_at(headers, ["宽", "宽(cm)", "宽度"])
    height_at = _header_at(headers, ["高", "高(cm)", "高度"])
    waybill_at = _header_at(headers, ["运单号"])
    ticket_at = _header_at(headers, ["货件编号", "FBA号", "FBA货件号"])
    bill_at = _header_at(headers, ["入库计费重"])
    boxes: list[dict[str, Any]] = []
    bills: dict[str, Decimal] = {}
    waybill = ""
    for row in grid[header_at + 1 :]:
        box_id = _text_id(_cell(row, box_at))
        weight = _num(_cell(row, weight_at))
        is_box = bool(box_id) and weight is not None and "入库计费重" not in box_id
        if is_box:
            current = str(_cell(row, waybill_at) or "").strip()
            if current:
                waybill = current
        ticket = str(_cell(row, ticket_at) or "").strip() or waybill
        bill = _num(_cell(row, bill_at)) if bill_at is not None else None
        if bill is None:
            for index, cell in enumerate(row):
                if "入库计费重" in str(cell or ""):
                    bill = _num(row[index + 1] if index + 1 < len(row) else None)
                    break
        if ticket and bill is not None and bill > 0 and not is_box:
            bills.setdefault(ticket.strip().upper(), q(bill, 2))
        elif ticket and bill is not None and bill > 0 and bill_at is not None:
            bills.setdefault(ticket.strip().upper(), q(bill, 2))
        if not is_box:
            continue
        dims = [_num(_cell(row, length_at)), _num(_cell(row, width_at)), _num(_cell(row, height_at))]
        stored = [float(item) for item in dims if item is not None]
        boxes.append({
            "ticket": ticket.strip().upper(),
            "id": box_id.upper(),
            "weight": weight,
            "dims": stored if len(stored) == 3 else [],
        })
    return {"boxes": boxes, "bills": bills}


def parse_measure_file(path: Path) -> dict[str, Any]:
    parsed = parse_measure_grid(_grid(path))
    parsed["path"] = str(path)
    return parsed


def _measure_files(root: Path) -> list[Path]:
    found = []
    for path in _files(root):
        if path.suffix.lower() not in {".xlsx", ".xlsm"}:
            continue
        if _batch_of(path) != "13":
            continue
        text = str(path)
        if "货代入库" in text:
            continue
        if "货代计费重确认" not in text:
            continue
        found.append(path)
    return sorted(found)


def _csv_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _label_index(row: list[str]) -> tuple[int, str] | None:
    for index, cell in enumerate(row):
        text = _compact(cell)
        if any(text.startswith(_compact(name)) for name in ("包装箱长度", "包装箱宽度", "包装箱高度", "包装箱重量")):
            return index, text
        if text in {"箱号", "编号"}:
            return index, text
    return None


def parse_amazon_csv(path: Path) -> list[dict[str, Any]]:
    rows = list(csv.reader(io.StringIO(_csv_text(path))))
    slots: dict[int, dict[str, Any]] = {}
    units = {"length": "in", "weight": "lb"}
    for row in rows:
        found = _label_index(row)
        if found is None:
            continue
        index, label = found
        if "长度" in label:
            kind = "l"
            units["length"] = "cm" if ("cm" in label.lower() or "厘米" in label) else "in"
        elif "宽度" in label:
            kind = "w"
        elif "高度" in label:
            kind = "h"
        elif "重量" in label:
            kind = "kg"
            units["weight"] = "kg" if ("kg" in label.lower() or "千克" in label) else "lb"
        else:
            kind = "id"
        for col in range(index + 1, len(row)):
            slots.setdefault(col, {})[kind] = row[col]
    declared = []
    for slot in slots.values():
        ident = _text_id(slot.get("id"))
        if not _FBA_BOX.match(ident):
            continue
        try:
            raw = [D(slot.get("l")), D(slot.get("w")), D(slot.get("h")), D(slot.get("kg"))]
        except Exception:
            continue
        if units["length"] == "in":
            dims = [float(item * _INCH) for item in raw[:3]]
        else:
            dims = [float(item) for item in raw[:3]]
        kg = float(raw[3] * _LB) if units["weight"] == "lb" else float(raw[3])
        if kg <= 0 or any(item <= 0 for item in dims):
            continue
        declared.append({"id": ident.upper(), "dims": dims, "weight": kg})
    return declared


def _csv_files(root: Path) -> list[Path]:
    found = []
    for path in _files(root):
        if path.suffix.lower() != ".csv" or _batch_of(path) != "13":
            continue
        if "货代入库" in str(path):
            continue
        found.append(path)
    return sorted(found)


def summarize_batch13(root: Path) -> dict[str, Any]:
    measure_paths = _measure_files(root)
    csv_paths = _csv_files(root)
    missing = []
    if not measure_paths:
        missing.append("第13批/货代计费重确认文件")
    if not csv_paths:
        missing.append("第13批亚马逊货件 CSV")
    if missing:
        raise LayoutMissing("缺少复算文件：" + "、".join(missing))
    boxes: list[dict[str, Any]] = []
    bills: dict[str, Decimal] = {}
    usable_csv = []
    for path in measure_paths:
        parsed = parse_measure_file(path)
        boxes.extend(parsed["boxes"])
        for ticket, bill in parsed["bills"].items():
            bills.setdefault(ticket, bill)
    declared: dict[str, dict[str, Any]] = {}
    for path in csv_paths:
        rows = parse_amazon_csv(path)
        if not rows:
            continue
        usable_csv.append(path)
        for row in rows:
            declared[row["id"]] = row
    if not boxes or not bills:
        raise LayoutMissing("货代计费重确认文件里没有逐箱行或入库计费重")
    if not declared:
        raise LayoutMissing("第13批 CSV 里没有包装箱重量/箱号")
    by_ticket: dict[str, list[dict[str, Any]]] = {}
    for box in boxes:
        by_ticket.setdefault(box["ticket"], []).append(box)
    carry = Decimal("0")
    paired = 0
    matched_bills = 0
    for ticket, bill in bills.items():
        scans = by_ticket.get(ticket) or []
        if not scans:
            continue
        paired += 1
        line = Decimal("0")
        for scan in scans:
            line += chargeable(scan["weight"], scan["dims"])
        carry += q(bill, 2) - q(line, 2)
        if q(bill, 2) == round_up_half_kg(line):
            matched_bills += 1
    counts: dict[str, int] = {}
    for box in boxes:
        if _FBA_BOX.match(box["id"]):
            counts[box["id"]] = counts.get(box["id"], 0) + 1
    box_total = Decimal("0")
    matched_rows = 0
    for box in boxes:
        ident = box["id"]
        if not _FBA_BOX.match(ident) or counts.get(ident, 0) != 1:
            continue
        other = declared.get(ident)
        if other is None:
            continue
        box_total += chargeable(box["weight"], box["dims"]) - chargeable(other["weight"], other["dims"])
        matched_rows += 1
    return {
        "box_total": q(box_total, 2),
        "matched_rows": matched_rows,
        "carry": q(carry, 2),
        "bill_count": paired,
        "bills_matched": matched_bills,
        "measure_files": [str(path) for path in measure_paths],
        "csv_files": [str(path) for path in usable_csv],
    }


def _sku_total(rows: list[list[Any]]) -> int | None:
    for row in rows[:6]:
        for cell in row:
            text = _compact(cell)
            if "SKU总数" not in text:
                continue
            found = re.search(r"(\d+)", text)
            if found:
                return int(found.group(1))
    return None


def _is_label(value: Any) -> bool:
    text = _compact(value)
    return bool(text) and any(text.startswith(_compact(prefix)) for prefix in _LABELS)


def sta_sheets(root: Path) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    missing = []
    for batch, expected in _STA_N.items():
        paths = [
            path for path in _files(root)
            if path.suffix.lower() in {".xlsx", ".xlsm"}
            and _batch_of(path) == batch
            and "send to amazon" in path.name.lower()
        ]
        hit = False
        for path in sorted(paths):
            for _title, rows in _sheets(path):
                total = _sku_total(rows)
                if total != expected:
                    continue
                hit = True
                label_rows = list(range(expected + 7, expected + 12))
                labels_ok = True
                for excel_row in label_rows:
                    row = rows[excel_row - 1] if excel_row - 1 < len(rows) else []
                    lead = next((cell for cell in row if str(cell or "").strip()), "")
                    if not _is_label(lead):
                        labels_ok = False
                found.append({
                    "batch": batch,
                    "n": expected,
                    "path": str(path),
                    "rows": rows,
                    "label_rows": label_rows,
                    "labels_ok": labels_ok,
                })
        if not hit:
            missing.append(f"第{batch}批 Send to Amazon（SKU 总数 {expected}）")
    if missing:
        raise LayoutMissing("缺少 STA 表：" + "、".join(missing))
    return found


def _header_field(value: Any) -> str:
    text = _compact(value).replace("*", "").replace("(", "").replace(")", "")
    if text.startswith("SKU简称") or text == "SKU":
        return "sku"
    if "发货总数" in text:
        return "qty"
    if "单箱装量" in text:
        return "per"
    if "空纸箱" in text:
        return "tare"
    if "单箱毛重" in text:
        return "gross"
    return ""


def cl2_net(root: Path) -> dict[str, Any]:
    candidates = []
    for path in _files(root):
        if "发货录入" not in path.name or path.suffix.lower() not in {".xlsx", ".xlsm"}:
            continue
        for _title, rows in _sheets(path):
            header = None
            mapping: dict[str, int] = {}
            for index, row in enumerate(rows[:15]):
                mapping = {}
                for col, cell in enumerate(row):
                    field = _header_field(cell)
                    if field and field not in mapping:
                        mapping[field] = col
                if {"sku", "qty", "gross"} <= set(mapping):
                    header = index
                    break
            if header is None:
                continue
            for row in rows[header + 1 :]:
                sku = str(row[mapping["sku"]] if mapping["sku"] < len(row) else "")
                if "CL2" not in sku.upper():
                    continue
                qty = _num(row[mapping["qty"]] if mapping["qty"] < len(row) else None)
                per = _num(row[mapping["per"]]) if "per" in mapping and mapping["per"] < len(row) else None
                gross = _num(row[mapping["gross"]] if mapping["gross"] < len(row) else None)
                tare = _num(row[mapping["tare"]]) if "tare" in mapping and mapping["tare"] < len(row) else None
                if qty is None or gross is None or tare is None or qty <= 0:
                    continue
                if per is not None and per > 0 and qty % per == 0:
                    boxes = int(qty / per)
                else:
                    boxes = int(qty)
                total_gross = gross if boxes > 1 and gross >= Decimal("100") else gross * boxes
                net = q(total_gross - tare * boxes, 1)
                candidates.append({
                    "path": str(path),
                    "batch": _batch_of(path),
                    "gross": q(total_gross, 1),
                    "boxes": boxes,
                    "tare": tare,
                    "net": net,
                })
    if not candidates:
        raise LayoutMissing("发货录入样表里没有 CL2 行")
    preferred = [item for item in candidates if item["batch"] == "13"] or candidates
    exact = [item for item in preferred if item["net"] == Decimal("254.4")]
    return (exact or preferred)[0]


def placement_table() -> dict[str, Any]:
    payload = json.loads(policy_path().read_text(encoding="utf-8"))
    fees = payload["placement_fees"]
    return {"source_url": str(fees.get("source_url") or ""), "classes": fees["classes"]}


def assemble(root: Path | None = None) -> dict[str, Any]:
    """目录在但缺文件时抛 LayoutMissing。"""
    base = root or realdata_root()
    if not base.is_dir():
        raise LayoutMissing(f"realdata 目录不存在：{base}")
    return {
        "batch13": summarize_batch13(base),
        "sta": sta_sheets(base),
        "cl2": cl2_net(base),
        "placement": placement_table(),
    }
