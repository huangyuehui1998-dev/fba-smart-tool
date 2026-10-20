"""箱唛 PDF 文件名解析。

示例：第二票外箱贴US-7TH-9810-PETBEDMAT-FBA19GQW64C7-SCK4.pdf
  -> 第二票 / 序号2 / 仓库 SCK4 / 货件 FBA19GQW64C7
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

_TICKET_PREFIX_RE = re.compile(r"^(第[零一二三四五六七八九十百\d]+票)")
_FBA_ID_RE = re.compile(r"(FBA[A-Z0-9]{9,})", re.IGNORECASE)

_CHN_DIGIT = {
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


@dataclass(frozen=True)
class BoxLabelPdfMeta:
    ticket_prefix: str = ""
    ticket_num: Optional[int] = None
    warehouse: str = ""
    shipment_id: str = ""


def chinese_numeral_to_int(text: str) -> Optional[int]:
    s = str(text or "").strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if s.startswith("十"):
        rest = s[1:]
        return 10 + (_CHN_DIGIT.get(rest, 0) if rest else 0)
    if "十" in s:
        tens_part, _, ones_part = s.partition("十")
        tens = _CHN_DIGIT.get(tens_part, 1) if tens_part else 1
        ones = _CHN_DIGIT.get(ones_part, 0) if ones_part else 0
        return tens * 10 + ones
    if len(s) == 1 and s in _CHN_DIGIT:
        return _CHN_DIGIT[s]
    return None


def parse_box_label_pdf_name(filename: str) -> BoxLabelPdfMeta:
    stem = Path(str(filename or "")).stem
    if not stem:
        return BoxLabelPdfMeta()

    ticket_prefix = ""
    ticket_num: Optional[int] = None
    m_ticket = _TICKET_PREFIX_RE.match(stem)
    if m_ticket:
        ticket_prefix = m_ticket.group(1)
        ticket_num = chinese_numeral_to_int(ticket_prefix[1:-1])

    shipment_id = ""
    warehouse = ""
    m_fba = _FBA_ID_RE.search(stem)
    if m_fba:
        shipment_id = m_fba.group(1).upper()
        tail = stem[m_fba.end() :].lstrip("-_")
        if tail:
            warehouse = tail.split("-")[-1].strip().upper()

    return BoxLabelPdfMeta(
        ticket_prefix=ticket_prefix,
        ticket_num=ticket_num,
        warehouse=warehouse,
        shipment_id=shipment_id,
    )


def _chinese_ticket_prefix(n: int) -> str:
    if n <= 0:
        return f"第{n}票"
    digits = "零一二三四五六七八九"
    if n < 10:
        cn = digits[n]
    elif n < 20:
        cn = "十" + (digits[n % 10] if n % 10 else "")
    elif n < 100:
        tens, ones = divmod(n, 10)
        cn = digits[tens] + "十" + (digits[ones] if ones else "")
    else:
        cn = str(n)
    return f"第{cn}票"


def ticket_prefix_for_pair(pair: Any, fallback_index: int) -> str:
    """仅返回票序，如「第二票」。"""
    pdf_name = str(getattr(pair, "pdf_name", "") or "")
    meta = parse_box_label_pdf_name(pdf_name)
    if meta.ticket_prefix:
        return meta.ticket_prefix
    return _chinese_ticket_prefix(fallback_index)


def column_label_for_pair(pair: Any, fallback_index: int) -> str:
    """生成工人装箱单列标题，优先读 PDF 文件名中的「第N票」。"""
    pdf_name = str(getattr(pair, "pdf_name", "") or "")
    meta = parse_box_label_pdf_name(pdf_name)
    wh = str(getattr(pair, "warehouse_code", "") or meta.warehouse or "UNKN").strip()
    if meta.ticket_prefix:
        return f"{meta.ticket_prefix} {wh}"
    return f"{_chinese_ticket_prefix(fallback_index)} {wh}"


def _ticket_label_from_index(ticket_index: int, warehouse: str) -> str:
    wh = str(warehouse or "UNKN").strip()
    return f"{_chinese_ticket_prefix(ticket_index)} {wh}"


def ticket_sort_num_for_pair(pair: Any, fallback_index: int) -> int:
    """票序数字，用于排序（第二票 -> 2）。"""
    pdf_name = str(getattr(pair, "pdf_name", "") or "")
    meta = parse_box_label_pdf_name(pdf_name)
    if meta.ticket_num is not None:
        return meta.ticket_num
    return fallback_index


def warehouse_ticket_rank(pairs: List[Any]) -> Dict[str, int]:
    """仓库代码 -> 票序（用于货代表排序）。"""
    rank: Dict[str, int] = {}
    for i, pair in enumerate(sort_pairs_by_box_label_pdf(pairs), start=1):
        wh = str(getattr(pair, "warehouse_code", "") or "").strip()
        if wh and wh not in rank:
            rank[wh] = ticket_sort_num_for_pair(pair, i)
    return rank


def sort_pairs_by_box_label_pdf(pairs: List[Any]) -> List[Any]:
    """按文件名中的票序排序；无票序时保持原顺序。"""

    def _key(idx_pair: tuple[int, Any]) -> tuple:
        idx, pair = idx_pair
        meta = parse_box_label_pdf_name(str(getattr(pair, "pdf_name", "") or ""))
        if meta.ticket_num is not None:
            return (0, meta.ticket_num, idx)
        return (1, idx, 0)

    indexed = list(enumerate(pairs))
    indexed.sort(key=_key)
    return [p for _, p in indexed]
