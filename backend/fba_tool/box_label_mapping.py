"""Step 2 本地箱号 ↔ 亚马逊 FBA 箱唛 ↔ 目的仓 映射。"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import pandas as pd

from fba_tool.fba_parser import simplify_sku
from fba_tool.shipment_validator import ShipmentPair


def format_local_box_label(box_no: int, prefix: str = "Box") -> str:
    return f"{prefix}-{int(box_no):02d}"


def contents_signature(contents: Dict[str, int]) -> Tuple[Tuple[str, int], ...]:
    return tuple(sorted((str(k).strip(), int(v)) for k, v in contents.items() if int(v) > 0))


@dataclass
class AmazonBox:
    amazon_box_no: int
    fba_box_id: str
    warehouse_code: str
    shipment_id: str
    contents: Dict[str, int]  # simplified SKU -> qty
    raw_contents: Dict[str, int] = field(default_factory=dict)


@dataclass
class BoxLabelMatch:
    local_box_no: int
    local_box_label: str
    fba_box_id: str
    amazon_box_no: int
    warehouse_code: str
    shipment_id: str
    match_method: str
    contents: Dict[str, int] = field(default_factory=dict)


@dataclass
class BoxLabelMappingResult:
    ok: bool
    matches: List[BoxLabelMatch] = field(default_factory=list)
    unmapped_local: List[int] = field(default_factory=list)
    unmapped_amazon: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def local_box_contents(editor_df: pd.DataFrame) -> Dict[int, Dict[str, int]]:
    if editor_df.empty:
        return {}
    grouped: Dict[int, Dict[str, int]] = defaultdict(dict)
    for _, row in editor_df.iterrows():
        box = int(row["箱号"])
        sku = str(row["SKU简称"]).strip()
        qty = int(row["数量"])
        if qty > 0 and sku:
            grouped[box][sku] = grouped[box].get(sku, 0) + qty
    return {k: dict(v) for k, v in sorted(grouped.items())}


def collect_amazon_boxes(pairs: List[ShipmentPair]) -> List[AmazonBox]:
    boxes: List[AmazonBox] = []
    for pair in pairs:
        csv = pair.csv
        fba_by_box: Dict[int, str] = dict(csv.box_fba_ids)
        if csv.box_specs is not None and not csv.box_specs.empty and "FBA箱号" in csv.box_specs.columns:
            for _, spec in csv.box_specs.iterrows():
                box_no = int(spec["箱号"])
                fba_id = str(spec.get("FBA箱号") or "").strip()
                if fba_id:
                    fba_by_box[box_no] = fba_id

        for box_no, raw_skus in sorted(csv.box_data.items()):
            simplified: Dict[str, int] = defaultdict(int)
            for sku, qty in raw_skus.items():
                short = simplify_sku(str(sku))
                simplified[short] += int(qty)
            boxes.append(
                AmazonBox(
                    amazon_box_no=int(box_no),
                    fba_box_id=fba_by_box.get(int(box_no), ""),
                    warehouse_code=pair.warehouse_code,
                    shipment_id=pair.shipment_id,
                    contents=dict(simplified),
                    raw_contents=dict(raw_skus),
                )
            )
    return boxes


def match_local_to_amazon_boxes(
    editor_df: pd.DataFrame,
    pairs: List[ShipmentPair],
    *,
    local_prefix: str = "Box",
) -> BoxLabelMappingResult:
    local_boxes = local_box_contents(editor_df)
    amazon_boxes = collect_amazon_boxes(pairs)
    result = BoxLabelMappingResult(ok=True)

    if not local_boxes:
        result.ok = False
        result.errors.append("❌ 本地装箱方案为空，无法建立贴标映射。")
        return result
    if not amazon_boxes:
        result.ok = False
        result.errors.append("❌ 亚马逊货件未解析到有效箱数据，无法建立贴标映射。")
        return result

    amazon_by_sig: Dict[Tuple[Tuple[str, int], ...], List[AmazonBox]] = defaultdict(list)
    for ab in amazon_boxes:
        amazon_by_sig[contents_signature(ab.contents)].append(ab)

    used_amazon: set[Tuple[str, int]] = set()

    def _amazon_key(ab: AmazonBox) -> Tuple[str, int]:
        return (ab.shipment_id, ab.amazon_box_no)

    for local_no, contents in sorted(local_boxes.items()):
        sig = contents_signature(contents)
        candidates = [c for c in amazon_by_sig.get(sig, []) if _amazon_key(c) not in used_amazon]
        if not candidates:
            result.unmapped_local.append(local_no)
            result.errors.append(
                f"❌ 本地 {format_local_box_label(local_no, local_prefix)} 无法在亚马逊 CSV 中找到内容一致的箱（"
                f"{_contents_summary(contents)}）。"
            )
            continue

        chosen = candidates[0]
        if len(candidates) > 1:
            result.warnings.append(
                f"⚠️ 本地 {format_local_box_label(local_no, local_prefix)} 存在多个内容相同的亚马逊箱，"
                f"已自动匹配 {chosen.fba_box_id or f'U{chosen.amazon_box_no:03d}'}。"
            )

        used_amazon.add(_amazon_key(chosen))
        result.matches.append(
            BoxLabelMatch(
                local_box_no=local_no,
                local_box_label=format_local_box_label(local_no, local_prefix),
                fba_box_id=chosen.fba_box_id,
                amazon_box_no=chosen.amazon_box_no,
                warehouse_code=chosen.warehouse_code,
                shipment_id=chosen.shipment_id,
                match_method="content",
                contents=dict(contents),
            )
        )

    for ab in amazon_boxes:
        if _amazon_key(ab) not in used_amazon:
            label = ab.fba_box_id or f"U{ab.amazon_box_no:03d}"
            result.unmapped_amazon.append(label)
            result.warnings.append(
                f"⚠️ 亚马逊箱 {label}（{ab.warehouse_code}）未匹配到本地箱号。"
            )

    if result.unmapped_local:
        result.ok = False
    return result


def _contents_summary(contents: Dict[str, int]) -> str:
    parts = [f"{sku}×{qty}" for sku, qty in sorted(contents.items()) if qty > 0]
    return "，".join(parts) if parts else "空箱"


def build_factory_long_with_mapping(
    editor_df: pd.DataFrame,
    mapping: BoxLabelMappingResult,
) -> pd.DataFrame:
    cols = [
        "本地箱号",
        "产品名称",
        "数量",
        "FBA箱号",
        "目的仓",
        "货件编号",
        "贴标说明",
        "仓库代码",
        "纸箱编号",
    ]
    if editor_df.empty:
        return pd.DataFrame(columns=cols)

    match_by_local = {m.local_box_no: m for m in mapping.matches}
    rows: List[Dict] = []
    work = editor_df.copy()
    work["箱号"] = work["箱号"].astype(int)
    work["SKU简称"] = work["SKU简称"].astype(str)
    grouped = work.groupby(["箱号", "SKU简称"], as_index=False)["数量"].sum()

    for _, row in grouped.iterrows():
        box_no = int(row["箱号"])
        sku = str(row["SKU简称"]).strip()
        qty = int(row["数量"])
        if qty <= 0 or not sku:
            continue
        m = match_by_local.get(box_no)
        fba_id = m.fba_box_id if m else ""
        wh = m.warehouse_code if m else ""
        sid = m.shipment_id if m else ""
        label_hint = f"贴 {fba_id} → {wh}" if fba_id and wh else ""
        rows.append(
            {
                "本地箱号": format_local_box_label(box_no),
                "产品名称": sku,
                "数量": qty,
                "FBA箱号": fba_id,
                "目的仓": wh,
                "货件编号": sid,
                "贴标说明": label_hint,
                "仓库代码": wh,
                "纸箱编号": box_no,
            }
        )

    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols)


def mapping_to_records(mapping: BoxLabelMappingResult) -> List[Dict]:
    records: List[Dict] = []
    for m in mapping.matches:
        records.append(
            {
                "本地箱号": m.local_box_label,
                "本地箱序号": m.local_box_no,
                "FBA箱号": m.fba_box_id,
                "亚马逊箱序号": m.amazon_box_no,
                "目的仓": m.warehouse_code,
                "货件编号": m.shipment_id,
                "装箱内容": _contents_summary(m.contents),
                "匹配方式": m.match_method,
            }
        )
    return records
