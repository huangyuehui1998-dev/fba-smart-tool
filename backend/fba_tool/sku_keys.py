"""S9-step3：SKU / MSKU 大小写统一（公共函数）。

规则：
- 存储时保留原始写法（显示、导出都用原始写法）；
- 匹配时一律用 sku_key() 规范化：全角转半角（NFKC）、去首尾空白、casefold；
- 亚马逊的 Seller SKU 本身区分大小写（Amazon 官方文档：“Both SKU and Amazon SKU values are case-sensitive.”），
  只差大小写的两个 SKU 理论上可以并存，所以匹配时如果有多个只差大小写的候选：
  原样完全相同的优先；否则报冲突（SkuCaseConflict / ambiguous），不静默任选一个。
"""
from __future__ import annotations

import unicodedata
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, TypeVar

V = TypeVar("V")


def sku_text(value: Any) -> str:
    """原始写法：只去首尾空白（含全角空格、NBSP），不改大小写。"""
    return str(value if value is not None else "").strip()


def sku_key(value: Any) -> str:
    """匹配用的规范键：NFKC（全角转半角）→ 去首尾空白 → casefold。"""
    return unicodedata.normalize("NFKC", str(value if value is not None else "")).strip().casefold()


class SkuCaseConflict(ValueError):
    """同一个规范键对应多个只差大小写（或全角/半角）的 SKU，且没有原样完全相同的一条。"""

    def __init__(self, sku: Any, candidates: Iterable[str]) -> None:
        self.sku = sku_text(sku)
        self.candidates = sorted({str(c) for c in candidates})
        super().__init__(
            f"SKU「{self.sku}」在产品库里有多条只差大小写/全角半角的记录：{'、'.join(self.candidates)}，"
            "无法确定是哪一条，没有自动选择；请先在产品库里确认（改名或删除多余的一条）"
        )


def pick_candidate(sku: Any, candidates: Iterable[str]) -> Optional[str]:
    """在候选（已按规范键命中的原始写法）里选一个：原样相同优先；只有一个就用它；多个就报冲突。"""
    text = sku_text(sku)
    cands = list(dict.fromkeys(str(c) for c in candidates))
    if not cands:
        return None
    if text in cands:
        return text
    stripped = [c for c in cands if sku_text(c) == text]
    if len(stripped) == 1:
        return stripped[0]
    if len(cands) == 1:
        return cands[0]
    raise SkuCaseConflict(text, cands)


def lookup_sku_detail(mapping: Mapping[str, V], sku: Any) -> Tuple[Optional[V], str, List[str]]:
    """在以原始 SKU 为键的字典里查：返回 (值, 方式, 候选)。方式：exact / normalized / ambiguous / miss。"""
    text = sku_text(sku)
    if not text:
        return None, "miss", []
    if text in mapping:
        return mapping[text], "exact", [text]
    key = sku_key(text)
    cands = [k for k in mapping if sku_key(k) == key]
    if len(cands) == 1:
        return mapping[cands[0]], "normalized", cands
    if len(cands) > 1:
        return None, "ambiguous", sorted(cands)
    return None, "miss", []


def lookup_sku(mapping: Mapping[str, V], sku: Any, default: Optional[V] = None) -> Optional[V]:
    """同 lookup_sku_detail，只要值；冲突（ambiguous）或没找到返回 default，不任选。"""
    val, how, _ = lookup_sku_detail(mapping, sku)
    return val if how in ("exact", "normalized") else default


def matching_texts(sku: Any, texts: Iterable[Any]) -> List[str]:
    """S9-step4-fix3：在一批原始写法（如装箱表各行的 SKU）里找与 sku 对应的写法：
    原样相同的优先（只取原样那一种）；否则规范键唯一命中时取它；多个只差大小写的候选 → 返回 []（不任选）。"""
    text = sku_text(sku)
    if not text:
        return []
    uniq = list(dict.fromkeys(sku_text(t) for t in texts if sku_text(t)))
    if text in uniq:
        return [text]
    key = sku_key(text)
    cands = [t for t in uniq if sku_key(t) == key]
    return cands if len(cands) == 1 else []


def case_conflict_message(groups: Iterable[Iterable[str]], where: str = "本票") -> str:
    """只差大小写 / 全角半角的 SKU 组 → 提示文字（按原样分别处理，不合并）。"""
    parts = ["、".join(g) for g in groups]
    return (f"{where}里有只差大小写/全角半角的 SKU：{'；'.join(parts)}。按原样分别取资料，没有合并，"
            "请确认是不是同一个产品（亚马逊 SKU 区分大小写）。")


def case_conflicts(skus: Iterable[Any]) -> Dict[str, List[str]]:
    """找出只差大小写/全角半角的 SKU 组：{规范键: [原始写法…]}（每组至少 2 个不同写法）。"""
    groups: Dict[str, List[str]] = {}
    for s in skus:
        text = sku_text(s)
        if not text:
            continue
        lst = groups.setdefault(sku_key(text), [])
        if text not in lst:
            lst.append(text)
    return {k: sorted(v) for k, v in groups.items() if len(v) > 1}
