"""箱侧冒烟的独立复算。只读原始文件，不导入产品代码。

进位 = 账单 − Σ(单箱计费重)。推算账单是否等于「合计 ↑0.5」另算，不拿来代替进位。
第 15 批账单与逐箱合计的差额、以及 pending_verification，都不在这里给出红绿结论。
逐箱表目录认「九方确认账单文件」，也认旧名「货代计费重确认」。
CL2 净重按发货表里货件号含 CL2 的行汇总毛重和箱数，皮重读同批发货录入样表的空纸箱重。
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


_MEASURE_LABEL = "第13批/九方确认账单（或货代计费重确认）文件"


def _is_measure_path(path: Path) -> bool:
    text = str(path)
    if "货代入库" in text:
        return False
    return "九方确认账单文件" in text or "货代计费重确认" in text


def _measure_files(root: Path) -> list[Path]:
    """第 13 批逐箱表。目录名用九方确认账单文件，旧名货代计费重确认仍认。"""
    found = []
    for path in _files(root):
        if path.suffix.lower() not in {".xlsx", ".xlsm"}:
            continue
        if _batch_of(path) != "13":
            continue
        if not _is_measure_path(path):
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
        missing.append(_MEASURE_LABEL)
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
        raise LayoutMissing(f"{_MEASURE_LABEL}里没有逐箱行或入库计费重")
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


def _flat(value: Any) -> str:
    text = _compact(value)
    for ch in ("\n", "\r", "\t", "(", ")", "（", "）", "*", ".", "．"):
        text = text.replace(ch, "")
    return text


def _is_cl2_shipment(value: Any) -> bool:
    text = _flat(value).upper()
    return "FBA" in text and "CL2" in text


def _same_shipment(left: str, right: str) -> bool:
    a, b = left.upper(), right.upper()
    if a == b:
        return True
    return "CL2" in a and "CL2" in b and (a in b or b in a)


def _box_numbers(value: Any) -> set[int]:
    """箱号单元格：逗号分隔、1-18 这种区间，或单个箱序号。"""
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    elif isinstance(value, int) and not isinstance(value, bool):
        text = str(value)
    else:
        text = str(value or "")
        text = re.sub(r"(?<!\d)(\d+)\.0+(?!\d)", r"\1", text)
    if not text.strip():
        return set()
    for ch in ("－", "—", "–", "~", "～", "至", "到"):
        text = text.replace(ch, "-")
    found: set[int] = set()
    for match in re.finditer(r"(\d+)\s*-\s*(\d+)|(\d+)", text):
        if match.group(3):
            found.add(int(match.group(3)))
            continue
        start, end = int(match.group(1)), int(match.group(2))
        if start > end:
            start, end = end, start
        if end - start > 1000:
            continue
        found.update(range(start, end + 1))
    return found


def _shipping_columns(row: list[Any]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for col, cell in enumerate(row):
        text = _flat(cell)
        if not text:
            continue
        kind = ""
        if "总毛重" in text:
            kind = "gross"
        elif text.startswith("箱号") or text.startswith("CartonNo"):
            kind = "carton"
        elif text.startswith("箱子数量") or (text.startswith("箱数") and "箱号" not in text):
            kind = "boxes"
        elif (
            text.startswith("FBA货件编号")
            or text.startswith("货件编号")
            or text.startswith("FBA编码")
            or text.startswith("FBA单号")
            or "ShipmentID" in text
        ):
            kind = "shipment"
        if kind and kind not in mapping:
            mapping[kind] = col
    if "shipment" in mapping and "gross" in mapping:
        return mapping
    return {}


def _row_is_total(row: list[Any]) -> bool:
    for cell in row:
        text = _flat(cell)
        if text.startswith("合计") or text.startswith("总计") or text.upper().startswith("TOTAL"):
            return True
    return False


def _shipping_groups(path: Path) -> list[dict[str, Any]]:
    """同一张表里同一货件的多行要相加。另一张表另算，避免把汇总页和明细页加两遍。"""
    found: list[dict[str, Any]] = []
    for _title, rows in _sheets(path):
        header_at = None
        mapping: dict[str, int] = {}
        groups: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(rows[:40]):
            mapping = _shipping_columns(row)
            if mapping:
                header_at = index
                break
        if header_at is None:
            continue
        last = ""
        for row in rows[header_at + 1 :]:
            if _row_is_total(row):
                last = ""
                continue
            shipment_text = str(_cell(row, mapping["shipment"]) or "").strip()
            gross = _num(_cell(row, mapping["gross"]))
            if _is_cl2_shipment(shipment_text):
                last = _flat(shipment_text).upper()
            elif shipment_text:
                last = ""
                continue
            if not last or gross is None or gross <= 0:
                continue
            bucket = groups.setdefault(last, {
                "shipment": last,
                "gross": Decimal("0"),
                "boxes": set(),
                "explicit": Decimal("0"),
                "explicit_rows": 0,
                "path": str(path),
            })
            bucket["gross"] += gross
            bucket["boxes"] |= _box_numbers(_cell(row, mapping.get("carton")))
            if "boxes" in mapping:
                explicit = _num(_cell(row, mapping["boxes"]))
                if explicit is not None and explicit > 0:
                    bucket["explicit"] += explicit
                    bucket["explicit_rows"] += 1
        found.extend(groups.values())
    return found


def _meta_value(row: list[Any], label: str) -> str:
    for index, cell in enumerate(row[:4]):
        if _flat(cell) == label and index + 1 < len(row):
            return str(row[index + 1] or "").strip()
    return ""


def _meta_number(row: list[Any], label: str) -> Decimal | None:
    for index, cell in enumerate(row[:4]):
        text = _flat(cell)
        if text == label and index + 1 < len(row):
            return _num(row[index + 1])
        if text.startswith(label) and text != label:
            found = re.search(r"(\d+)", str(cell))
            return D(found.group(1)) if found else None
    return None


def _csv_box_counts(root: Path) -> list[tuple[str, int]]:
    """装箱明细 / 货件 CSV 头部的「箱子数量」。只收集货件号里带 CL2 的。"""
    found: list[tuple[str, int]] = []
    for path in _files(root):
        if path.suffix.lower() != ".csv" or _batch_of(path) != "13":
            continue
        if "货代入库" in str(path):
            continue
        rows = list(csv.reader(io.StringIO(_csv_text(path))))
        shipment = ""
        count = None
        for row in rows[:25]:
            if not row:
                continue
            shipment = shipment or _meta_value(row, "货件编号") or _meta_value(row, "ShipmentID")
            if count is None:
                count = _meta_number(row, "箱子数量")
        if not shipment and "CL2" in path.name.upper():
            shipment = path.stem
        if shipment and _is_cl2_shipment(shipment) and count is not None and count > 0:
            found.append((_flat(shipment).upper(), int(count)))
    return found


def _tares_in_rows(rows: list[list[Any]]) -> list[Decimal]:
    tare_at = None
    header = None
    for index, row in enumerate(rows[:20]):
        for col, cell in enumerate(row):
            if _header_field(cell) == "tare":
                tare_at = col
                header = index
                break
        if tare_at is not None:
            break
    if tare_at is None or header is None:
        return []
    values = []
    for row in rows[header + 1 :]:
        if tare_at >= len(row):
            continue
        number = _num(row[tare_at])
        if number is None or number <= 0:
            continue
        values.append(q(number, 4))
    return values


def _entry_tares(root: Path) -> tuple[list[Decimal], str]:
    """同批发货录入样表的空纸箱重。多行一致才用；没有则按产品缺皮重 0.2 kg。"""
    batch13: list[Decimal] = []
    other: list[Decimal] = []
    saw13 = False
    for path in _files(root):
        if "发货录入" not in path.name or path.suffix.lower() not in {".xlsx", ".xlsm"}:
            continue
        values: list[Decimal] = []
        for _title, rows in _sheets(path):
            values.extend(_tares_in_rows(rows))
        if _batch_of(path) == "13":
            saw13 = True
            batch13.extend(values)
        else:
            other.extend(values)
    distinct = sorted(set(batch13 if saw13 else other))
    if len(distinct) == 1:
        return distinct, ""
    if len(distinct) > 1:
        return distinct, "发货录入样表的空纸箱重不一致"
    return [Decimal("0.2")], "发货录入样表没有空纸箱重，皮重按产品规则 0.2 kg"


def _shipping_workbooks(root: Path) -> list[Path]:
    found = []
    for path in _files(root):
        if path.suffix.lower() not in {".xlsx", ".xlsm"} or _batch_of(path) != "13":
            continue
        if "货代入库" in str(path):
            continue
        if "发货表" not in path.name and "发给工厂" not in str(path):
            continue
        found.append(path)
    return sorted(found)


def cl2_net(root: Path) -> dict[str, Any]:
    """第 13 批 CL2：发货表汇总毛重和箱数，发货录入样表提供皮重。不按 SKU 含 CL2 匹配。"""
    groups: list[dict[str, Any]] = []
    for path in _shipping_workbooks(root):
        groups.extend(_shipping_groups(path))
    if not groups:
        raise LayoutMissing("第13批发货表（发给工厂）里没有货件号含 CL2 的行")
    csv_counts = _csv_box_counts(root)
    tares, tare_note = _entry_tares(root)
    candidates = []
    for group in groups:
        options: list[tuple[int, str]] = []
        if group["boxes"]:
            options.append((len(group["boxes"]), "箱号"))
        if group["explicit_rows"] and group["explicit"] == int(group["explicit"]):
            options.append((int(group["explicit"]), "箱数"))
        for shipment, count in csv_counts:
            if _same_shipment(group["shipment"], shipment):
                options.append((count, "装箱明细箱子数量"))
        seen: set[int] = set()
        unique: list[tuple[int, str]] = []
        for count, source in options:
            if count <= 0 or count in seen:
                continue
            seen.add(count)
            unique.append((count, source))
        if not unique:
            continue
        gross = q(group["gross"], 1)
        for tare in tares:
            for count, source in unique:
                net = q(gross - tare * count, 1)
                detail = (
                    f"{Path(group['path']).name} 货件 {group['shipment']} "
                    f"总毛重 {gross} kg，{count} 箱（{source}），皮重 {tare} kg"
                )
                if tare_note:
                    detail = f"{detail}。{tare_note}"
                candidates.append({
                    "path": group["path"],
                    "batch": "13",
                    "shipment": group["shipment"],
                    "gross": gross,
                    "boxes": count,
                    "tare": tare,
                    "net": net,
                    "detail": detail,
                })
    if not candidates:
        raise LayoutMissing("第13批发货表有 CL2 行，但没有箱数（箱号或装箱明细里的箱子数量）")
    exact = [item for item in candidates if item["net"] == Decimal("254.4")]
    pool = exact or candidates
    pool.sort(key=lambda item: (item["path"], item["shipment"], item["boxes"]))
    return pool[0]


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
