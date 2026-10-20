"""实测文件适配器。新增来源只加一个 sniff/parse，接口不变。"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Protocol

from fba_tool.carton_math import inches_to_cm, lb_to_kg, q


class MeasurementAdapter(Protocol):
    name: str

    def sniff(self, filename: str, head: str) -> bool: ...

    def parse(self, data: bytes) -> List[Dict[str, Any]]: ...


class ParseError(ValueError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _xlsx_headers(data: bytes) -> List[str]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        first = next(ws.iter_rows(max_row=1, values_only=True), ())
        return [str(cell or "").strip() for cell in first]
    finally:
        wb.close()


def _xlsx_rows(data: bytes) -> List[Dict[str, Any]]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), data_only=True)
    try:
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    if not rows:
        return []
    headers = [str(cell or "").strip() for cell in rows[0]]
    out = []
    for index, row in enumerate(rows[1:], start=2):
        if not any(cell not in (None, "") for cell in row):
            continue
        out.append({"_row": index, **{headers[i]: row[i] if i < len(row) else None for i in range(len(headers))}})
    return out


def _pick(row: Dict[str, Any], names: List[str]) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def _fnum(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(q(value, 3))


_WEIGHT_ALIASES = ["单箱实重", "实重", "实重(kg)", "重量"]
_VOL_ALIASES = ["单箱材重", "材重", "体积重"]
_CHARGE_ALIASES = ["计费重", "单箱计费重"]
_BOX_ALIASES = ["外箱号", "FBA箱号", "箱号"]
_WAYBILL_ALIASES = ["运单号"]
_BILL_LABELS = ("入库计费重", "入库体积", "渠道最小计费重")


def _grid(data: bytes) -> List[List[Any]]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), data_only=True)
    try:
        ws = wb.worksheets[0]
        return [list(row) for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def _header_index(headers: List[str], names: List[str]) -> int | None:
    for name in names:
        if name in headers:
            return headers.index(name)
    return None


def _cell(row: List[Any], index: int | None) -> Any:
    if index is None or index >= len(row):
        return None
    return row[index]


def _normalize_box_id(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _is_pure_number(text: str) -> bool:
    return bool(text) and text.isdigit()


def _as_decimal(value: Any):
    if value in (None, ""):
        return None
    try:
        return q(value, 6)
    except Exception:
        return None


def _label_value(row: List[Any], label: str) -> Any:
    for index, cell in enumerate(row):
        if label in str(cell or ""):
            return row[index + 1] if index + 1 < len(row) else None
    return None


class JiufangBoxAdapter:
    name = "jiufang_box_xlsx"

    def sniff(self, filename: str, head: str) -> bool:
        name = filename.lower()
        return "九方" in filename or "jiufang" in name or ("外箱号" in head and "实重" in head and "入库计费重" not in head)

    def parse(self, data: bytes) -> List[Dict[str, Any]]:
        from fba_tool.carton_math import chargeable_kg_rounded, volumetric_kg

        grid = _grid(data)
        header_at = None
        headers: List[str] = []
        for index, row in enumerate(grid):
            headers = [str(cell or "").strip() for cell in row]
            if "外箱号" in headers or "FBA箱号" in headers:
                header_at = index
                break
        if header_at is None:
            return []
        weight_at = _header_index(headers, _WEIGHT_ALIASES)
        box_at = _header_index(headers, _BOX_ALIASES)
        if weight_at is None and box_at is not None and _header_index(headers, ["长", "长(cm)", "长度"]) is not None:
            raise ParseError("缺少列：单箱实重")
        length_at = _header_index(headers, ["长", "长(cm)", "长度"])
        width_at = _header_index(headers, ["宽", "宽(cm)", "宽度"])
        height_at = _header_index(headers, ["高", "高(cm)", "高度"])
        vol_at = _header_index(headers, _VOL_ALIASES)
        charge_at = _header_index(headers, _CHARGE_ALIASES)
        waybill_at = _header_index(headers, _WAYBILL_ALIASES)
        fba_at = _header_index(headers, ["货件编号", "FBA号", "FBA货件号"])
        sku_at = _header_index(headers, ["SKU", "SKU简称"])
        rows: List[Dict[str, Any]] = []
        bill = {"bill_chargeable_kg": None, "channel_min_kg": None, "inbound_cbm": None}
        waybill = ""
        for offset, raw in enumerate(grid[header_at + 1 :], start=header_at + 2):
            if not any(cell not in (None, "") for cell in raw):
                continue
            label_hit = any(label in "".join(str(cell or "") for cell in raw) for label in _BILL_LABELS)
            if label_hit:
                charge = _as_decimal(_label_value(raw, "入库计费重"))
                volume = _as_decimal(_label_value(raw, "入库体积"))
                minimum = _as_decimal(_label_value(raw, "渠道最小计费重"))
                if charge is not None:
                    bill["bill_chargeable_kg"] = float(charge)
                if volume is not None:
                    bill["inbound_cbm"] = float(volume)
                if minimum is not None:
                    bill["channel_min_kg"] = float(minimum)
                if charge is None and volume is None and minimum is None:
                    rows.append({"kind": "issue", "source_row": offset, "message": "表尾数字无法读取"})
                continue
            box_id = _normalize_box_id(_cell(raw, box_at))
            weight = _as_decimal(_cell(raw, weight_at)) if weight_at is not None else None
            if box_id and weight is not None:
                length = _as_decimal(_cell(raw, length_at))
                width = _as_decimal(_cell(raw, width_at))
                height = _as_decimal(_cell(raw, height_at))
                current_waybill = str(_cell(raw, waybill_at) or "").strip()
                if current_waybill:
                    waybill = current_waybill
                volumetric = None
                if length is not None and width is not None and height is not None:
                    volumetric = volumetric_kg(length, width, height)
                column_vol = _as_decimal(_cell(raw, vol_at)) if vol_at is not None else None
                chargeable = chargeable_kg_rounded(weight, volumetric if volumetric is not None else weight)
                if column_vol is not None:
                    volumetric = column_vol
                rows.append({
                    "kind": "box",
                    "fba_id": str(_cell(raw, fba_at) or ""),
                    "fba_box_id": box_id,
                    "sku": str(_cell(raw, sku_at) or ""),
                    "length_cm": None if length is None else float(length),
                    "width_cm": None if width is None else float(width),
                    "height_cm": None if height is None else float(height),
                    "weight_kg": float(weight),
                    "volumetric_kg": None if volumetric is None else float(volumetric),
                    "chargeable_kg": float(chargeable),
                    "waybill": waybill,
                    "match_status": "invalid_id" if _is_pure_number(box_id) else "",
                    "source_row": offset,
                    "raw": {"waybill": waybill},
                    "raw_unit": "cm_kg",
                })
                continue
            if box_id and weight is None and weight_at is not None and _cell(raw, weight_at) not in (None, ""):
                rows.append({"kind": "issue", "source_row": offset, "message": "单箱实重不是数字"})
                continue
            rows.append({"kind": "issue", "source_row": offset, "message": "未识别的行"})
        if any(value is not None for value in bill.values()):
            rows.append({
                "kind": "forwarder_bill",
                "fba_id": waybill,
                "waybill": waybill,
                "bill_chargeable_kg": bill["bill_chargeable_kg"],
                "channel_min_kg": bill["channel_min_kg"],
                "inbound_cbm": bill["inbound_cbm"],
                "forwarder": "jiufang",
            })
        return rows


class SendBoxAdapter:
    name = "send_box_xlsx"

    def sniff(self, filename: str, head: str) -> bool:
        name = filename.lower()
        return "send" in name or ("外箱号" in head and "SEND" in head.upper())

    def parse(self, data: bytes) -> List[Dict[str, Any]]:
        return JiufangBoxAdapter().parse(data)


class ManualBoxAdapter:
    name = "manual_xlsx"

    def sniff(self, filename: str, head: str) -> bool:
        return "手工" in filename or ("外箱号" in head and "重量" in head and "实重" not in head)

    def parse(self, data: bytes) -> List[Dict[str, Any]]:
        return JiufangBoxAdapter().parse(data)


class ForwarderBillAdapter:
    name = "forwarder_bill_xlsx"

    def sniff(self, filename: str, head: str) -> bool:
        return "入库计费重" in head or "货代表" in filename

    def parse(self, data: bytes) -> List[Dict[str, Any]]:
        rows = []
        seen = set()
        for raw in _xlsx_rows(data):
            fba_id = str(_pick(raw, ["货件编号", "FBA货件号", "FBA号"]) or "").strip()
            bill = _pick(raw, ["入库计费重"])
            box_id = _pick(raw, ["外箱号", "FBA箱号"])
            if box_id not in (None, ""):
                rows.append({
                    "kind": "box",
                    "fba_id": fba_id,
                    "fba_box_id": str(box_id).strip(),
                    "length_cm": _fnum(_pick(raw, ["长", "长(cm)"])),
                    "width_cm": _fnum(_pick(raw, ["宽", "宽(cm)"])),
                    "height_cm": _fnum(_pick(raw, ["高", "高(cm)"])),
                    "weight_kg": _fnum(_pick(raw, ["单箱实重", "实重", "实重(kg)", "重量"])),
                    "chargeable_kg": _fnum(_pick(raw, ["单箱计费重", "计费重"])),
                    "source_row": raw["_row"],
                    "raw": {},
                    "raw_unit": "cm_kg",
                })
            if fba_id and bill not in (None, "") and fba_id not in seen:
                seen.add(fba_id)
                rows.append({
                    "kind": "forwarder_bill",
                    "fba_id": fba_id,
                    "bill_chargeable_kg": float(q(bill, 2)),
                    "channel_min_kg": _fnum(_pick(raw, ["渠道最低"])),
                    "forwarder": str(_pick(raw, ["货代"]) or ""),
                })
        return rows


class FeePreviewAdapter:
    name = "fee_preview_txt"

    def sniff(self, filename: str, head: str) -> bool:
        lowered = head.lower()
        return filename.lower().endswith((".txt", ".tsv")) or "product-size-tier" in lowered or "item-package-weight" in lowered

    def parse(self, data: bytes) -> List[Dict[str, Any]]:
        text = data.decode("utf-8-sig")
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            raise ParseError("Fee Preview 文件是空的")
        headers = [cell.strip() for cell in lines[0].split("\t")]
        lowered = [cell.lower() for cell in headers]
        weight_names = ["item-package-weight", "weight", "item_package_weight"]
        if not any(name in lowered for name in weight_names):
            raise ParseError("缺少列：item-package-weight")
        def col(*names: str) -> int | None:
            for name in names:
                if name in lowered:
                    return lowered.index(name)
            return None
        sku_i = col("sku")
        asin_i = col("asin")
        long_i = col("longest-side")
        med_i = col("median-side")
        short_i = col("shortest-side")
        weight_i = col("item-package-weight", "weight")
        dim_unit_i = col("unit-of-dimension")
        weight_unit_i = col("unit-of-weight")
        tier_i = col("product-size-tier", "product-size-weight-band")
        store_i = col("amazon-store", "marketplace")
        rows = []
        for line_no, line in enumerate(lines[1:], start=2):
            cells = line.split("\t")
            def take(index: int | None) -> str:
                if index is None or index >= len(cells):
                    return ""
                return cells[index].strip()
            dim_unit = take(dim_unit_i).lower()
            weight_unit = take(weight_unit_i).lower()
            def length(index: int | None):
                raw = take(index)
                if not raw:
                    return None
                number = q(raw, 2)
                if dim_unit in {"inches", "inch", "in"}:
                    return float(inches_to_cm(number))
                return float(number)
            weight_raw = take(weight_i)
            if not weight_raw:
                raise ParseError(f"第{line_no}行缺少列：item-package-weight")
            weight = q(weight_raw, 3)
            if weight_unit in {"pounds", "pound", "lb", "lbs"}:
                weight = lb_to_kg(weight)
            store = take(store_i).upper()
            if store in {"AMAZON.COM", "US", "ATVPDKIKX0DER"}:
                marketplace = "US"
            elif store in {"AMAZON.CA", "CA", "A2EUQ1WTGCTBG2"}:
                marketplace = "CA"
            else:
                marketplace = store or "US"
            rows.append({
                "kind": "item",
                "sku": take(sku_i),
                "asin": take(asin_i),
                "marketplace": marketplace,
                "longest_cm": length(long_i),
                "median_cm": length(med_i),
                "shortest_cm": length(short_i),
                "weight_kg": float(q(weight, 3)),
                "size_tier": take(tier_i),
                "source_row": line_no,
                "raw": {"line": line},
            })
        return rows


ADAPTERS: List[MeasurementAdapter] = [
    FeePreviewAdapter(),
    ForwarderBillAdapter(),
    JiufangBoxAdapter(),
    SendBoxAdapter(),
    ManualBoxAdapter(),
]


def head_text(filename: str, data: bytes) -> str:
    if filename.lower().endswith((".txt", ".tsv", ".csv")) or not data.startswith(b"PK"):
        return data[:4000].decode("utf-8", errors="ignore")
    try:
        return " ".join(_xlsx_headers(data))
    except Exception:
        return ""


def detect_adapter(filename: str, data: bytes) -> MeasurementAdapter:
    head = head_text(filename, data)
    for adapter in ADAPTERS:
        if adapter.sniff(filename, head):
            return adapter
    raise ParseError("认不出实测文件格式")
