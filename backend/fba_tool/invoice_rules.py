"""S4 发票导出的确定性规则（方案 v8 §3.5）。

货代适配器（invoice_export.py）只管“往哪个格子写”，规则全部在这里：
- 箱号区间：按亚马逊 U 号（FBA…U000001 → 1）排序，同一 SKU、连续、单箱数量/重量/尺寸都相同的箱合并成“起-止”；
- 混装箱（一箱多个 SKU）：每个 SKU 单独一行，箱号写同一个号，单箱重只写在该箱第一行，避免重复计重；
- 申报价：fba_tool.product_fields.resolve_declared_price（D-01：领星售价 > 手填 > 领星 price/landed_price > 旧数据；
  D-12 修订：领星售价比正常价 regular_price / 90 天内非促销价低 5% 以上时按正常价，并提示 promo_price_not_used）；
  价格警告/拦截用 customs_package.price_checks（与 s2-fix2 同一口径）；
- 采购价照抄产品库（CNY，不换算）；申报币种固定 USD；
- 文本数字（'39.99'、'50.0'）一律写成数值格；
- 品类 fishing 的 SKU 缺报关配置（HS / 中文品名 / HS 申报要素模板）直接拦截，并列出缺的项；
  其它品类缺发票必填字段同样拦截。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Tuple

DECLARED_CURRENCY = "USD"
_U_RE = re.compile(r"U0*(\d+)$")

# 发票必填字段（产品库字段名 → 中文名）
REQUIRED_PRODUCT_FIELDS = {
    "english_name": "英文品名",
    "chinese_name": "中文品名",
    "brand": "品牌",
    "hs_code": "清关编码",
    "invoice_unit": "单位",
}


class InvoiceBlocked(ValueError):
    """导出被拦截（缺价格、缺报关配置等）。blocking 是逐条原因。"""

    def __init__(self, blocking: List[Dict[str, Any]]):
        self.blocking = blocking
        super().__init__("；".join(b["message"] for b in blocking))


def to_number(v: Any) -> Any:
    """文本数字写成数值：'39.99' → 39.99，'50.0' → 50.0，'92' → 92；不是数字原样返回。"""
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    s = str(v).strip().replace(",", "")
    if not s:
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return v
    return int(d) if d == d.to_integral_value() and "." not in s and "e" not in s.lower() else float(d)


# 发票数量列：整数值写成 int。价格、重量、尺寸保持小数。
QTY_INT_FIELDS = frozenset({"qty_per_box", "total_qty", "box_count", "pcs_per_set"})
NUMBER_FIELDS = QTY_INT_FIELDS | frozenset({
    "declared_price",
    "purchase_price",
    "total_declared_value_usd",
    "unit_weight_kg",
    "box_weight",
    "length",
    "width",
    "height",
})


def coerce_invoice_number(field_key: str | None, value: Any) -> Any:
    """文本数字按列写成数值。整数数量写成 int，申报价这类小数保持 float。"""
    if not field_key or field_key not in NUMBER_FIELDS or value in (None, ""):
        return value
    num = to_number(value)
    if isinstance(num, bool) or not isinstance(num, (int, float)):
        return value
    if field_key in QTY_INT_FIELDS and float(num) == int(num):
        return int(num)
    if isinstance(num, int):
        return num
    return float(num)


# 这些列看起来像数字，导出仍保持文本（前导零、海关编码位数不能丢）。
TEXT_KEEP_FIELDS = frozenset({
    "hs_code",
    "dest_hs_code",
    "zip",
    "postal_code",
    "phone",
    "tel",
    "mobile",
    "box_range",
    "shipment_id",
    "reference_id",
    "fba_id",
    "sku",
    "fnsku",
    "asin",
})

_TEXT_HEADER_BITS = (
    "海关编码", "清关编码", "hscode", "hs编码", "h.s.code",
    "邮编", "邮政编码", "postalcode", "zipcode",
    "电话", "手机", "联系电话", "telephone", "phone", "mobile",
)
_QTY_HEADER_BITS = (
    "单箱内数量", "每箱数量", "箱内数量", "sku个数", "totalqty", "总数量", "商品总数",
    "产品个数", "numberofunits", "unit个数", "商品数量", "每套个数", "总箱数", "总件数",
    "预报件数", "箱数", "件数",
)
_FLOAT_HEADER_BITS = (
    "申报单价", "单价", "declaredvalue", "单个货值", "货值", "采购单价", "采购价",
    "总申报金额", "申报总价", "listingvalue", "单件实重", "单件重量", "单件毛重",
    "单箱重量", "单箱毛重", "单箱实重", "包装箱重量", "货箱重量", "毛重", "净重",
    "实重", "重量", "cbm", "体积",
)


def _norm_header(text: Any) -> str:
    s = str(text or "").replace("（", "(").replace("）", ")").replace("\xa0", " ").replace("\n", "")
    return re.sub(r"[\s*：:]+", "", s).casefold()


def header_number_kind(text: Any) -> str:
    """表头属于数量、价格/重量/尺寸，还是必须保持文本的 HS/邮编/电话。空字符串表示不转。"""
    key = _norm_header(text)
    if not key:
        return ""
    if any(bit in key for bit in _TEXT_HEADER_BITS) or key in {"zip", "tel", "hs"}:
        return "text"
    dim = re.sub(r"\(cm\)|\(kg\)|\(lb\)", "", key)
    if dim in {"长", "宽", "高", "length", "width", "height"} or any(
        bit in dim for bit in ("长度", "宽度", "高度", "length", "width", "height")
    ):
        return "float"
    if dim.endswith(("长", "宽", "高")) and (
        "(cm)" in key or dim.startswith(("l", "w", "h", "单", "货", "外")) or len(dim) <= 3
    ):
        return "float"
    if any(bit in key for bit in _QTY_HEADER_BITS) or key in {"个数", "qty", "quantity", "数量", "ctns", "pcs"}:
        if any(bad in key for bad in ("重量", "货值", "金额", "单价", "价格", "编码", "邮编", "电话")):
            return ""
        return "qty"
    if any(bit in key for bit in _FLOAT_HEADER_BITS) or key in {"weight", "kg"}:
        return "float"
    return ""


def coerce_export_number(value: Any, *, field_key: str | None = None, header: Any = None) -> Any:
    """导出写入前把数量/价格/重量/尺寸从文本转成数值。HS、邮编、电话保持原文本。"""
    if value in (None, ""):
        return value
    key = str(field_key or "").strip()
    if key in TEXT_KEEP_FIELDS:
        return value
    if key in QTY_INT_FIELDS:
        kind = "qty"
    elif key in NUMBER_FIELDS:
        kind = "float"
    else:
        kind = header_number_kind(header)
    if kind == "qty":
        return coerce_invoice_number("total_qty", value)
    if kind == "float":
        return coerce_invoice_number("declared_price", value)
    return value


def dec(v: Any) -> Optional[Decimal]:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v).strip().replace(",", ""))
    except InvalidOperation:
        return None


def round2(v: Any) -> float:
    return float(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def box_no_from_fba_id(fba_box_id: str) -> Optional[int]:
    m = _U_RE.search(str(fba_box_id or "").strip().upper())
    return int(m.group(1)) if m else None


def cbm(l: Any, w: Any, h: Any) -> float:
    v = Decimal(str(l)) * Decimal(str(w)) * Decimal(str(h)) / Decimal(1000000)
    return float(v.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------- 箱
@dataclass
class Box:
    no: int                    # U 号
    fba_box_id: str
    items: List[Tuple[str, int]]  # [(fnsku, qty)]，按 CSV 顺序
    weight: Optional[float]    # kg
    dims: Tuple[Optional[float], Optional[float], Optional[float]] = (None, None, None)  # cm
    weight_source: str = "csv"

    @property
    def mixed(self) -> bool:
        return len(self.items) > 1


def boxes_from_csv(shipment, measured: Optional[Dict[str, Dict[str, Any]]] = None) -> List[Box]:
    """CSV → 箱列表（按 U 号排序）。measured：{FBA箱号: {weight, length, width, height}}，有就用实测值（九方单箱数据）。"""
    items: Dict[int, List[Tuple[str, int]]] = {}
    for _, r in shipment.box_items.iterrows():
        q = int(r["数量"])
        if q <= 0:
            continue
        items.setdefault(int(r["箱号"]), []).append((str(r["FNSKU"]).strip().upper(), q))
    specs = {}
    if not shipment.box_specs.empty:
        for _, r in shipment.box_specs.iterrows():
            specs[int(r["箱号"])] = r
    out: List[Box] = []
    for col_no, its in items.items():
        fid = str(shipment.box_fba_ids.get(col_no) or "").strip().upper()
        no = box_no_from_fba_id(fid) or col_no
        sp = specs.get(col_no)
        w = float(sp["实重(kg)"]) if sp is not None and sp.get("实重(kg)") == sp.get("实重(kg)") else None
        dims = tuple(float(sp[k]) if sp is not None and sp.get(k) == sp.get(k) else None for k in ("长(cm)", "宽(cm)", "高(cm)"))
        src = "csv"
        m = (measured or {}).get(fid)
        if m:
            w = float(m["weight"])
            dims = (float(m["length"]), float(m["width"]), float(m["height"]))
            src = "measured"
        out.append(Box(no=no, fba_box_id=fid, items=its, weight=w, dims=dims, weight_source=src))
    out.sort(key=lambda b: b.no)
    return out


@dataclass
class RangeRow:
    start: int
    end: int
    fnsku: str
    qty: int               # 区间内该 SKU 合计
    weight: Optional[float]  # 单箱重（混装箱非首行为 None）
    dims: Tuple[Optional[float], Optional[float], Optional[float]]
    mixed: bool = False

    @property
    def label(self) -> str:
        return str(self.start) if self.start == self.end else f"{self.start}-{self.end}"


def _range_spec_key(
    weight: Optional[float],
    dims: Tuple[Optional[float], Optional[float], Optional[float]],
) -> Tuple[Optional[float], Tuple[Optional[float], Optional[float], Optional[float]]]:
    """合并键按两位小数比。10.004 和 10.001 是同一箱规，7.50 和 7.60 仍然分开。"""

    def rounded(value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        return round2(value)

    return (rounded(weight), tuple(rounded(item) for item in dims))


def box_ranges(boxes: List[Box]) -> List[RangeRow]:
    """合并连续箱号：同一 SKU、单箱数量相同、单箱重相同、尺寸相同才合并；混装箱单独成行。"""
    rows: List[RangeRow] = []
    prev: Optional[Tuple] = None
    for b in boxes:
        if b.mixed:
            for i, (sku, q) in enumerate(b.items):
                rows.append(RangeRow(b.no, b.no, sku, q, b.weight if i == 0 else None, b.dims, mixed=True))
            prev = None
            continue
        sku, q = b.items[0]
        key = (sku, q, *_range_spec_key(b.weight, b.dims))
        if prev is not None and prev == key and rows and rows[-1].end == b.no - 1 and not rows[-1].mixed:
            rows[-1].end = b.no
            rows[-1].qty += q
        else:
            rows.append(RangeRow(b.no, b.no, sku, q, b.weight, b.dims))
        prev = key
    return rows


def sku_totals(boxes: List[Box]) -> List[Tuple[str, int]]:
    """按 SKU 汇总数量，顺序 = 第一次出现的箱号顺序。"""
    out: Dict[str, int] = {}
    for b in boxes:
        for sku, q in b.items:
            out[sku] = out.get(sku, 0) + q
    return list(out.items())


# ---------------------------------------------------------------- 产品 / 价格 / 拦截
def _invoice_unit(inv: Dict[str, Any], product: Dict[str, Any]) -> str:
    unit = str(inv.get("unit") or "").strip()
    if unit:
        return unit
    from fba_tool.user_config import param

    fallback = param("invoice_unit_fallback_declare_unit", True)
    if fallback in (False, 0, "0", "false", "False"):
        return ""
    return str(product.get("declare_unit") or "").strip()


def invoice_english_name(catalog_name: Any, fallback: Any = "") -> str:
    """英文品名用产品库。产品库没有时才用领星/货件标题。"""
    name = str(catalog_name or "").strip()
    if name.lower() == "nan":
        name = ""
    if name:
        return name
    other = str(fallback or "").strip()
    if other.lower() == "nan":
        return ""
    return other


def invoice_fields(product: Dict[str, Any]) -> Dict[str, Any]:
    """产品库 → 发票字段。发票专用字段放在 extra_data.invoice（单位、每套个数、采购价、英文材质/用途、目的港 HS）。"""
    p = dict(product or {})
    extra = p.get("extra") or {}
    ed = p.get("extra_data")
    if isinstance(ed, str) and ed.strip():
        try:
            import json as _json

            ed = _json.loads(ed)
        except ValueError:
            ed = {}
    if isinstance(ed, dict):
        extra = {**ed, **extra}
    inv = dict(extra.get("invoice") or {})
    inv.update(p.get("invoice") or {})
    return {
        "sku": p.get("sku") or "",
        "fnsku": str(p.get("fnsku") or "").upper(),
        "asin": p.get("asin") or "",
        "english_name": invoice_english_name(p.get("english_name")),
        "chinese_name": p.get("chinese_name") or "",
        "brand": p.get("brand") or "",
        "model": p.get("model_name") or inv.get("model") or "无",
        "material_cn": p.get("material") or "",
        "material_en": inv.get("material_en") or "",
        "purpose_cn": p.get("purpose") or "",
        "purpose_en": inv.get("purpose_en") or "",
        "hs_code": str(inv.get("dest_hs_code") or p.get("hs_code") or ""),
        "invoice_unit": _invoice_unit(inv, p),
        "pcs_per_set": to_number(inv.get("pcs_per_set")) or 1,
        "purchase_price": inv.get("purchase_price"),
        "has_battery": inv.get("has_battery") or "否",
        "category": p.get("category") or "",
    }


def _tagged_id(kind: str, text: str) -> str:
    """标识本身已经以 SKU / FNSKU 开头时不再加一遍，避免「SKU SKU-…」。"""
    raw = str(text or "").strip()
    if not raw:
        return ""
    if raw.casefold().startswith(kind.casefold()):
        return raw
    return f"{kind} {raw}"


def missing_price_label(*, sku: str = "", fnsku: str = "", fallback: str = "") -> str:
    """空申报价同时点名 SKU 和 FNSKU。只有一边时只列那一边；都没有再用原来的标识。"""
    sku_text = _tagged_id("SKU", sku)
    fnsku_text = _tagged_id("FNSKU", fnsku)
    if sku_text and fnsku_text:
        return f"{sku_text} / {fnsku_text}"
    if sku_text:
        return sku_text
    if fnsku_text:
        return fnsku_text
    return str(fallback or "").strip()


def unique_missing_price_labels(entries: Iterable[Tuple[str, str, str]]) -> List[str]:
    """同一 SKU 只出现一次。大小写或全角不同的写法并成一条，FNSKU 与 SKU 相同时不重复写。"""
    from fba_tool.sku_keys import sku_key

    order: List[str] = []
    grouped: Dict[str, Dict[str, Any]] = {}
    for sku, fnsku, fallback in entries:
        sku_text = str(sku or "").strip()
        fnsku_text = str(fnsku or "").strip()
        if sku_text and fnsku_text and sku_key(sku_text) == sku_key(fnsku_text):
            fnsku_text = ""
        token = sku_key(sku_text) or sku_key(fnsku_text) or sku_key(fallback)
        if not token:
            continue
        slot = grouped.get(token)
        if slot is None:
            grouped[token] = {"sku": sku_text, "fnskus": [], "fallback": fallback}
            order.append(token)
            slot = grouped[token]
        if fnsku_text and all(sku_key(fnsku_text) != sku_key(old) for old in slot["fnskus"]):
            slot["fnskus"].append(fnsku_text)
    labels: List[str] = []
    for token in order:
        slot = grouped[token]
        labels.append(missing_price_label(
            sku=slot["sku"],
            fnsku="、".join(slot["fnskus"]),
            fallback=str(slot["fallback"] or ""),
        ))
    return [label for label in labels if label]


def price_rows(products: Dict[str, Dict[str, Any]], fnskus: Iterable[str]) -> List[Dict[str, Any]]:
    from fba_tool.product_fields import resolve_declared_price

    rows = []
    for f in fnskus:
        p = products.get(f) or {}
        price, src = resolve_declared_price(p) if p else (None, "")
        dv = p.get("declared_value")
        # 与 master_db.customs_hints 同一口径（s2-fix2）：领星价被采用时，旧申报价作“历史申报价”，手填的再记“手填申报价”
        legacy = dv if (src.startswith("lingxing") and dv not in (None, "")) else None
        manual = dv if legacy is not None and (p.get("field_sources") or {}).get("declared_value") == "manual" else None
        if src == "legacy":
            legacy = dv
        from fba_tool.product_fields import promo_info

        promo = promo_info(p) if p else None  # D-12
        rows.append({"sku": f, "product_sku": str(p.get("sku") or "").strip(),
                     "fnsku": str(p.get("fnsku") or f or "").strip(),
                     "price_source": src or "none", "unit_price": price,
                     "legacy_price": legacy, "manual_price": manual, "raw_price": price,
                     "promo_price": promo["listing_price"] if promo else None})
    return rows


def check_products(products: Dict[str, Dict[str, Any]], fnskus: Iterable[str], *, required: Dict[str, str],
                   hs_templates: Optional[Dict[tuple, Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """缺产品 / 缺发票字段 / 钓鱼缺报关配置 → 拦截项。"""
    from fba_tool.hs_config import customs_config_missing, effective_category

    blocking: List[Dict[str, Any]] = []
    for f in fnskus:
        p = products.get(f)
        if not p:
            blocking.append({"code": "product_missing", "sku": f, "message": f"产品库里没有 {f}，不能导出"})
            continue
        fields = invoice_fields(p)
        if effective_category(p) == "fishing":
            miss = customs_config_missing(p, hs_templates)
            if miss:
                blocking.append({"code": "fishing_config_missing", "sku": f, "missing": miss,
                                 "message": f"钓鱼 SKU {f} 缺报关配置：{'、'.join(miss)}，不能导出（不会按宠物默认值填）"})
                continue
        miss = [label for k, label in required.items() if not str(fields.get(k) or "").strip()]
        if miss:
            blocking.append({"code": "invoice_field_missing", "sku": f, "missing": miss,
                             "message": f"{f} 缺发票必填字段：{'、'.join(miss)}"})
    return blocking


@dataclass
class InvoiceModel:
    forwarder: str
    shipment_id: str
    reference_id: str
    warehouse: str
    boxes: List[Box]
    ranges: List[RangeRow]
    lines: List[Dict[str, Any]]   # 每 SKU 一行：fnsku, qty, price, total, fields…
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    price_sources: List[Dict[str, Any]] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_qty(self) -> int:
        return sum(l["qty"] for l in self.lines)

    @property
    def total_value(self) -> float:
        return round2(sum(Decimal(str(l["total"])) for l in self.lines))


def build_model(*, forwarder: str, shipment, products: Dict[str, Dict[str, Any]], reference_id: str = "",
                warehouse: str = "", measured: Optional[Dict[str, Dict[str, Any]]] = None,
                required: Optional[Dict[str, str]] = None, hs_templates=None, meta: Optional[Dict[str, Any]] = None) -> InvoiceModel:
    """CSV + 产品库 → 发票模型；有拦截项时抛 InvoiceBlocked。products 以 FNSKU（大写）为键。"""
    from fba_tool.customs_package import price_checks

    products = {str(k).upper(): v for k, v in products.items()}
    boxes = boxes_from_csv(shipment, measured)
    if not boxes:
        raise InvoiceBlocked([{"code": "no_boxes", "message": "货件 CSV 里没有装箱数据"}])
    totals = sku_totals(boxes)
    fnskus = [f for f, _ in totals]
    blocking = check_products(products, fnskus, required=REQUIRED_PRODUCT_FIELDS if required is None else required,
                              hs_templates=hs_templates)
    sources, warnings, price_block = price_checks(price_rows(products, fnskus))
    blocking += price_block
    if measured is not None:
        ids = {b.fba_box_id for b in boxes}
        extra = sorted(k for k in measured if k not in ids)
        lack = [b.fba_box_id or str(b.no) for b in boxes if b.weight_source != "measured"]
        if extra or lack:
            blocking.append({"code": "measured_box_mismatch", "extra": extra, "missing": lack,
                             "message": "九方单箱数据和货件 CSV 的箱号对不上：" +
                                        (f"单箱数据里多出 {'、'.join(extra)}；" if extra else "") +
                                        (f"货件里这些箱没有实测值：{'、'.join(lack)}" if lack else "") +
                                        "。请核对外箱号，确认更正后再导出"})
    missing_w = [b.fba_box_id or str(b.no) for b in boxes if b.weight in (None, 0)]
    if missing_w:
        blocking.append({"code": "box_weight_missing", "message": "这些箱没有单箱重：" + "、".join(missing_w[:10])})
    if blocking:
        raise InvoiceBlocked(blocking)
    by_sku = {s["sku"]: s for s in sources}
    lines = []
    for f, q in totals:
        fields = invoice_fields(products[f])
        price = float(by_sku[f]["price"])
        lines.append({**fields, "fnsku": f, "qty": q, "price": price, "price_source": by_sku[f]["source"],
                      "listing_price": to_number(products[f].get("listing_price")),
                      "total": round2(Decimal(str(price)) * q)})
    return InvoiceModel(forwarder=forwarder, shipment_id=shipment.shipment_id, reference_id=reference_id,
                        warehouse=warehouse, boxes=boxes, ranges=box_ranges(boxes), lines=lines,
                        warnings=warnings, price_sources=sources, meta=dict(meta or {}))


# ---------------------------------------------------------------- 九方单箱数据（实测）
def read_jiufang_box_data(data: bytes, shipment_id: str, file_name: str = "",
                          box_id_fix: Optional[Dict[str, int]] = None) -> Dict[str, Dict[str, Any]]:
    """九方“单箱数据”表（序号/外箱号/单箱实重/长/宽/高）→ {FBA箱号: {weight, length, width, height}}。
    外箱号写 FBA…U000001 时直接用；只写 1、2、3 时按 {shipment_id}U00000n 补全。
    box_id_fix：用户确认过的外箱号更正（如九方把第 6 箱写成 12 → {"12": 6}），不确认就不改，导出时会被拦截。"""
    import io as _io

    import openpyxl

    wb = openpyxl.load_workbook(_io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = [tuple(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    hi = next((i for i, r in enumerate(rows[:10]) if r and "外箱号" in [str(x or "").strip() for x in r]), None)
    if hi is None:
        raise ValueError(f"{file_name or '单箱数据'} 里找不到“外箱号”表头")
    head = [str(x or "").strip() for x in rows[hi]]
    col = {k: head.index(k) for k in ("外箱号", "单箱实重", "长", "宽", "高") if k in head}
    if len(col) < 5:
        raise ValueError(f"{file_name or '单箱数据'} 缺列：" + "、".join(k for k in ("外箱号", "单箱实重", "长", "宽", "高") if k not in col))
    sid = str(shipment_id).strip().upper()
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows[hi + 1:]:
        raw = r[col["外箱号"]] if col["外箱号"] < len(r) else None
        if raw in (None, ""):
            continue
        s = str(int(raw) if isinstance(raw, float) and raw.is_integer() else raw).strip().upper()
        if box_id_fix and s in box_id_fix:
            s = str(int(box_id_fix[s]))
        if s.isdigit():
            s = f"{sid}U{int(s):06d}"
        elif not s.startswith("FBA"):
            continue
        if box_id_fix and s in box_id_fix:  # 界面按“多出的 FBA 箱号 → 箱序号”提交的更正（S7-fix1）
            s = f"{sid}U{int(box_id_fix[s]):06d}"
        out[s] = {k2: float(r[col[k1]]) for k1, k2 in (("单箱实重", "weight"), ("长", "length"), ("宽", "width"), ("高", "height"))}
    return out
