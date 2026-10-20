"""本地产品信息表：解析、查询、更新（非流程必选项）。"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fba_tool.app_paths import resolve_config_read, resolve_config_write
from fba_tool.sku_keys import sku_key, sku_text
from fba_tool.template_loader import templates_dir

CANONICAL_NAME = "产品信息表.csv"
EXAMPLE_MARK = "示例"  # D-19：产品信息表_示例.csv 只是格式示例（DEMO 值），不当成真实产品表读
SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-_]*(?:-FBA)?$", re.I)

DEFAULT_COL_MAP = {
    "sku": 2,
    "product_name": 1,
    "asin": 3,
    "fnsku": 4,
    "chinese_name": 6,
    "customs_name_cn": 7,
    "hs_code": 8,
    "material": 9,
    "unit_cost": 20,
}


@dataclass
class ProductRecord:
    sku: str
    product_name: str = ""
    asin: str = ""
    fnsku: str = ""
    chinese_name: str = ""
    customs_name_cn: str = ""
    hs_code: str = ""
    material: str = ""
    unit_cost: Optional[float] = None
    category: str = ""
    english_hint: str = ""

    def to_invoice_hints(self) -> Dict[str, Any]:
        return {
            "海关编码": self.hs_code,
            "中文品名": self.customs_name_cn or self.chinese_name,
            "英文品名": self.english_hint or self.customs_name_cn or self.chinese_name,
            "材料": self.material.replace("\n", "; "),
            "用途": "宠物用品",
            "品牌": _default_brand(),
            "单个货值": self.unit_cost,
        }


def _default_brand() -> str:
    """S9-step5：品牌不再写死在代码里；在 user_settings 的 parameters.default_brand 里配置，默认空（留空让人补）。"""
    from fba_tool.user_config import param

    return str(param("default_brand", "") or "").strip()


@dataclass
class ProductCatalog:
    source_path: Path
    records: Dict[str, ProductRecord] = field(default_factory=dict)
    row_count: int = 0

    def lookup_with_match(self, sku: str) -> tuple[Optional[ProductRecord], str]:
        """返回 (记录, 匹配方式)：exact / fuzzy / ambiguous / miss。

        子串匹配仅在候选唯一时采纳。命中多条时返回 ambiguous 且不给记录——
        宁可留空让人补，也不能把 PETBED-M 的报关品名/HS 安到 PETBED-MAT 上。
        """
        # S9-step4-fix3：记录按原样写法存；先原样，再规范键（NFKC + casefold）唯一命中，多个只差大小写 → ambiguous
        text = sku_text(sku)
        if not text:
            return None, "miss"
        if text in self.records:
            return self.records[text], "exact"
        key = sku_key(text)
        same = [rec for k, rec in self.records.items() if sku_key(k) == key]
        if len(same) == 1:
            return same[0], "exact"
        if len(same) > 1:
            return None, "ambiguous"
        candidates = [rec for k, rec in self.records.items() if key in sku_key(k) or sku_key(k) in key]
        if len(candidates) == 1:
            return candidates[0], "fuzzy"
        if len(candidates) > 1:
            return None, "ambiguous"
        return None, "miss"

    def lookup(self, sku: str) -> Optional[ProductRecord]:
        return self.lookup_with_match(sku)[0]

    def merge_for_skus(self, skus: List[str]) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for sku in skus:
            rec = self.lookup(sku)
            if not rec:
                continue
            for k, v in rec.to_invoice_hints().items():
                if v not in (None, "") and not merged.get(k):
                    merged[k] = v
        return merged


def load_catalog_config() -> dict:
    path = resolve_config_read("product_catalog.json")
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_catalog_config(filename: str) -> None:
    path = resolve_config_write("product_catalog.json")
    data = {
        "source_file": filename,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_example_catalog(path: Path) -> bool:
    """D-19：文件名带「示例」的产品信息表只是格式模板，自动查找时跳过。"""
    return EXAMPLE_MARK in Path(path).name


def find_catalog_path() -> Optional[Path]:
    """找本地真实产品信息表（可选）；没有就返回 None，程序照常运行（运行时只读 SQLite 主库）。"""
    cfg = load_catalog_config()
    if cfg.get("source_file"):
        p = templates_dir() / cfg["source_file"]
        if p.exists() and not is_example_catalog(p):
            return p
    canonical = templates_dir() / CANONICAL_NAME
    if canonical.exists():
        return canonical
    for p in sorted(templates_dir().glob("*产品信息表*")):
        if p.suffix.lower() in {".csv", ".xlsx", ".xls"} and not is_example_catalog(p):
            return p
    return None


def save_catalog_upload(file_bytes: bytes, filename: str) -> Path:
    templates_dir().mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix.lower() or ".csv"
    dest = templates_dir() / (CANONICAL_NAME if ext == ".csv" else f"产品信息表{ext}")
    dest.write_bytes(file_bytes)
    save_catalog_config(dest.name)
    return dest


def _cell(row: List[str], idx: int) -> str:
    if idx < 0 or idx >= len(row):
        return ""
    return str(row[idx] or "").strip()


def _to_float(v: str) -> Optional[float]:
    try:
        s = str(v).strip()
        if not s:
            return None
        return round(float(s), 2)
    except Exception:
        return None


def _detect_col_map(rows: List[List[str]]) -> Dict[str, int]:
    col_map = dict(DEFAULT_COL_MAP)
    for row in rows[:8]:
        for ci, cell in enumerate(row):
            val = str(cell or "").strip()
            if not val:
                continue
            low = val.lower()
            if low == "sku" or (low.startswith("sku") and "fnsku" not in low):
                col_map["sku"] = ci
            if "海关编码" in val or val.upper() == "HS CODE":
                col_map["hs_code"] = ci
            if val in ("材质", "材料") or val.endswith("材质"):
                col_map["material"] = ci
            if "商品报关" in val or val == "报关名称":
                col_map["customs_name_cn"] = ci
            if "中文名称" in val:
                col_map["chinese_name"] = ci
            if val in ("产品名称",) or val.endswith("产品名称"):
                col_map["product_name"] = ci
            if "产品成本" in val:
                col_map["unit_cost"] = ci
            if "fnsku" in low:
                col_map["fnsku"] = ci
            if low == "asin":
                col_map["asin"] = ci
    return col_map


def parse_catalog(path: Path) -> ProductCatalog:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = [["" if c is None else str(c) for c in row] for row in ws.iter_rows(values_only=True)]
        wb.close()
        return _parse_catalog_rows(rows, path)
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    if "\ufffd" in text and path.suffix.lower() == ".csv":
        for enc in ("gbk", "gb18030"):
            try:
                text = path.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue
    return _parse_catalog_rows(list(csv.reader(io.StringIO(text))), path)


def _parse_catalog_rows(rows: List[List[str]], path: Path) -> ProductCatalog:
    col = _detect_col_map(rows)
    records: Dict[str, ProductRecord] = {}
    count = 0
    for row in rows:
        sku = sku_text(_cell(row, col["sku"]))  # S9-step4-fix3：保留原样写法，不再转大写
        if not sku or sku_key(sku) in {"sku", "sku简称"}:
            continue
        if not SKU_RE.match(sku.replace(" ", "")):
            continue
        count += 1
        records[sku] = ProductRecord(
            sku=sku,
            product_name=_cell(row, col["product_name"]),
            asin=_cell(row, col["asin"]),
            fnsku=_cell(row, col["fnsku"]),
            chinese_name=_cell(row, col["chinese_name"]),
            customs_name_cn=_cell(row, col["customs_name_cn"]),
            hs_code=_cell(row, col["hs_code"]),
            material=_cell(row, col["material"]),
            unit_cost=_to_float(_cell(row, col["unit_cost"])),
            category=_cell(row, 0),
            english_hint=_cell(row, col["customs_name_cn"]) or _cell(row, 1),
        )
    return ProductCatalog(source_path=path, records=records, row_count=count)


def load_product_catalog(force_path: Path | None = None) -> Optional[ProductCatalog]:
    path = force_path or find_catalog_path()
    if not path or not path.exists():
        return None
    try:
        return parse_catalog(path)
    except Exception:
        return None


def extract_csv_skus(csv_bytes: bytes, file_name: str = "") -> List[str]:
    from fba_tool.shipment_parser import parse_csv_shipment

    ship = parse_csv_shipment(csv_bytes, file_name=file_name)
    if ship.box_items.empty:
        return []
    return sorted(ship.box_items["SKU"].astype(str).unique().tolist())


def lookup_sta_product_name(
    sku: str,
    *,
    amazon_meta: Dict[str, dict] | None = None,
    catalog: ProductCatalog | None = None,
) -> str:
    """Send to Amazon 商品名称：优先产品信息表「产品名称」，再 amazon 元数据。"""
    key = str(sku or "").strip()
    if not key:
        return ""
    cat = catalog
    rec_master = None
    try:
        from fba_tool.master_db import get_product_by_sku

        rec_master = get_product_by_sku(key)
    except Exception:
        rec_master = None
    if rec_master:
        return str(
            rec_master.get("english_name")
            or rec_master.get("model_name")
            or rec_master.get("chinese_name")
            or key
        ).strip()
    if cat:
        rec = cat.lookup(key)
        if rec:
            if rec.product_name:
                return rec.product_name
            if rec.chinese_name:
                return rec.chinese_name
    meta = (amazon_meta or {}).get(key, {})
    return str(meta.get("product_name") or key).strip()


def catalog_status_text() -> str:
    path = find_catalog_path()
    if not path:
        return "未检测到产品信息表（可选）"
    cat = load_product_catalog(path)
    if not cat:
        return f"已找到文件但解析失败：{path.name}"
    cfg = load_catalog_config()
    updated = cfg.get("updated_at", "内置/未知")
    return f"{path.name} · {cat.row_count} 条 SKU · 更新 {updated}"
