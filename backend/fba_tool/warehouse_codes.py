"""亚马逊 FBA 目的仓代码白名单 + 校验 + 多源提取。

用途：提升 Step 4 仓库代码识别准确率。
- BUILTIN_WAREHOUSE_CODES：内置常见美国 FBA 运营中心/分拣中心代码白名单。
- 用户可在 app_data/config/warehouse_codes.json 里补充新仓（新仓开出时自助添加），
  格式为字符串数组，例如 ["ABC1", "XYZ9"]。
- is_valid_warehouse_code：格式 + 白名单双重校验。
- pick_warehouse_code：从多个候选来源投票选出最可信的仓库代码。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Iterable, List, Optional, Tuple

from fba_tool.app_paths import resolve_config_read

# 亚马逊仓库代码格式：3 个字母 + 1~2 位数字（如 FWA4、ONT8、GYR2、MDW2）。
# 另有少量 4 字母的特殊设施（如 XUSE、KILN），单独收进白名单，不参与此格式判定。
WAREHOUSE_CODE_RE = re.compile(r"^[A-Z]{3}\d{1,2}$")

# 内置白名单（美国常见 FC / SC，来源于公开的亚马逊运营中心代码目录，持续可扩展）。
BUILTIN_WAREHOUSE_CODES: frozenset[str] = frozenset(
    {
        # AZ
        "PHX3", "PHX5", "PHX6", "PHX7", "PHX8", "PHX9", "TFC1", "GYR2", "GYR4",
        "DPX1", "DPX3", "DPX7", "DPX8", "TUS1", "TUS2", "RAZ1", "RPX1",
        # CA
        "LGB3", "LGB4", "LGB5", "LGB6", "LGB7", "LGB8", "LGB9", "OAK3", "OAK4",
        "OAK5", "OAK6", "OAK7", "OAK8", "ONT2", "ONT3", "ONT4", "ONT5", "ONT6",
        "ONT7", "ONT8", "ONT9", "SJC7", "SMF1", "SMF3", "SMF5", "SNA4", "SNA6",
        "SNA7", "SNA8", "SNA9", "KRB1", "SBD1", "SBD2", "SCK1", "SCK4", "FAT1",
        "LAX9", "LGB1", "LGB2", "XUSD", "XUSJ",
        # CO
        "DEN2", "DEN3", "DEN5", "DEN6", "DEN8",
        # CT
        "BDL1", "BDL2", "BDL3", "BDL5",
        # DC / DE
        "FWA3", "GSE2", "PHL1", "PHL3", "PHL7", "PHL8",
        # FL
        "JAX2", "JAX3", "JAX5", "LAL1", "MCO1", "MCO2", "MCO5", "MIA1", "MIA5",
        "MIA6", "TPA1", "TPA2", "TPA6",
        # GA
        "ATL2", "ATL5", "ATL6", "ATL7", "ATL8", "ATL9", "MGE1", "MGE3", "MGE5",
        "SAV1", "SAV3", "AGS1",
        # IL
        "MDW2", "MDW4", "MDW5", "MDW6", "MDW7", "MDW8", "MDW9", "STL4", "STL6",
        "STL7", "ORD2", "ORD5",
        # IN
        "IND1", "IND2", "IND3", "IND4", "IND5", "IND6", "IND7", "IND9", "SDF8",
        "XUSE", "MQJ1",
        # KS
        "MCI1", "MKC4", "MKC6", "TUL1", "XUSK",
        # KY
        "CVG1", "CVG2", "CVG3", "CVG5", "CVG8", "LEX1", "LEX2", "SDF1", "SDF2",
        "SDF4", "SDF6", "SDF7", "SDF9",
        # MD
        "BWI1", "BWI2", "BWI4", "BWI5", "BWI6", "DCA6", "MTN5", "MDT2",
        # MA
        "BOS1", "BOS3", "BOS7",
        # MI
        "DET1", "DET2", "DTW1", "DTW3", "DTW5", "GRR1",
        # MN
        "MSP1", "MSP5", "MSP6", "MSP7",
        # MS / MO
        "MEM2", "MEM6", "STL5", "STL8",
        # NV
        "LAS1", "LAS2", "LAS5", "LAS6", "LAS7", "RNO1", "RNO2", "RNO3", "RNO4",
        # NH / NJ
        "ABE8", "ACY1", "ACY2", "ACY5", "EWR4", "EWR5", "EWR6", "EWR7", "EWR8",
        "EWR9", "LGA6", "LGA7", "LGA8", "LGA9", "TEB3", "TEB6", "TEB9",
        # NY
        "JFK8", "BUF5", "SWF1", "SWF2",
        # NC
        "CLT2", "CLT3", "CLT4", "CLT5", "RDU2", "RDU4", "GSO1",
        # OH
        "CLE2", "CLE3", "CLE5", "CMH1", "CMH2", "CMH3", "CMH4", "CMH6", "LCK1",
        "DAY3", "MFC1", "TOL3", "PCW1",  # TOL3 Perrysburg、PCW1 Rossford（琪珞仓库表核对）
        # OK
        "OKC1", "OKC2", "TUL2",
        # OR
        "PDX5", "PDX6", "PDX7", "PDX9", "HIO9",
        # PA
        "ABE1", "ABE2", "ABE3", "ABE4", "ABE5", "AVP1", "AVP2", "AVP3", "AVP6",
        "AVP8", "MDT1", "PHL4", "PHL5", "PHL6", "PHL9", "PIT1", "PIT2", "PIT5",
        "XUSC", "XUSG",
        # SC
        "CAE1", "CAE3", "GSP1", "CHS1",
        # TN
        "BNA1", "BNA2", "BNA3", "BNA5", "CHA1", "CHA2", "MEM1", "MEM5", "MEM8",
        # TX
        "DAL3", "DAL6", "DAL9", "DFW6", "DFW7", "DFW8", "DFW9", "FTW1", "FTW2",
        "FTW3", "FTW4", "FTW5", "FTW6", "FTW7", "FTW8", "FTW9", "HOU2", "HOU3",
        "HOU6", "HOU7", "HOU8", "SAT1", "SAT2", "SAT4", "SAT5", "AUS2", "AUS3",
        "XUSB",
        # UT
        "SLC1", "SLC2", "SLC3", "SLC4", "DUT1",
        # VA
        "BWI7", "RIC1", "RIC2", "RIC3", "RIC5", "ORF2", "ORF3", "DCA4",
        # WA
        "BFI1", "BFI3", "BFI4", "BFI5", "BFI6", "BFI7", "FWA4", "GEG1", "GEG2",
        "PAE2", "SEA6", "SEA8",
        # WI
        "MKE1", "MKE2", "MKE5", "MKE6",
        # 4字母特殊设施 / IXD 入库中心
        "KILN", "XLX6", "IUSF", "IUSQ", "RYY2", "SUHB", "SUHD",
    }
)

USER_CONFIG_FILENAME = "warehouse_codes.json"


@lru_cache(maxsize=1)
def _user_warehouse_codes() -> frozenset[str]:
    """读取用户自定义仓库代码（app_data/config/warehouse_codes.json）。"""
    try:
        path = resolve_config_read(USER_CONFIG_FILENAME)
    except Exception:
        return frozenset()
    if not path or not path.exists():
        return frozenset()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return frozenset()
    codes: List[str] = []
    if isinstance(data, list):
        codes = [str(c) for c in data]
    elif isinstance(data, dict) and isinstance(data.get("codes"), list):
        codes = [str(c) for c in data["codes"]]
    return frozenset(normalize_code(c) for c in codes if str(c).strip())


def reload_user_warehouse_codes() -> None:
    """用户编辑白名单文件后可调用以清缓存。"""
    _user_warehouse_codes.cache_clear()


def _db_warehouse_codes() -> frozenset[str]:
    """产品库 fba_warehouse 表里的仓库代码（琪珞仓库表导入）。表不存在或读失败时返回空集。"""
    try:
        from fba_tool.warehouse_db import list_warehouse_codes

        return frozenset(normalize_code(c) for c in list_warehouse_codes(whitelist_only=True))
    except Exception:
        return frozenset()


def known_warehouse_codes() -> frozenset[str]:
    """fba_warehouse 表 + 内置 + 用户自定义的完整白名单。"""
    return _db_warehouse_codes() | BUILTIN_WAREHOUSE_CODES | _user_warehouse_codes()


def normalize_code(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().upper())


def matches_format(code: str) -> bool:
    """符合亚马逊仓库代码常规格式（3字母+1~2数字）。"""
    return bool(WAREHOUSE_CODE_RE.match(normalize_code(code)))


def is_valid_warehouse_code(code: str) -> bool:
    """白名单命中 或 符合标准格式 即视为有效。

    白名单优先；格式作为对未收录新仓的兜底（避免误杀真实新仓）。
    """
    norm = normalize_code(code)
    if not norm:
        return False
    if norm in known_warehouse_codes():
        return True
    return matches_format(norm)


def is_whitelisted(code: str) -> bool:
    """严格白名单命中（不含格式兜底）。"""
    return normalize_code(code) in known_warehouse_codes()


def extract_warehouse_from_text(text: str) -> str:
    """从任意文本中提取第一个"白名单命中"的仓库代码；无命中返回空串。

    只信任白名单命中，避免把 SKU 片段/日期误当仓库。
    """
    s = str(text or "").upper()
    known = known_warehouse_codes()
    # 先找白名单里出现的代码（按长度降序，避免子串误命中）
    for token in sorted(known, key=len, reverse=True):
        if re.search(rf"(?<![A-Z0-9]){re.escape(token)}(?![A-Z0-9])", s):
            return token
    return ""


def pick_warehouse_code(
    candidates: Iterable[Tuple[str, str]],
) -> Tuple[str, List[str]]:
    """多源投票选出最可信仓库代码。

    candidates: 可迭代的 (来源标签, 候选值) 列表，按可信度从高到低传入。
    返回：(选定代码, 警告信息列表)。

    规则：
      1. 优先选"白名单命中"的候选；多个白名单命中且不一致 → 取第一个（最高优先级源）并给出冲突警告。
      2. 无白名单命中时，取第一个"符合格式"的候选。
      3. 全部不可信 → 返回空串。
    """
    warnings: List[str] = []
    normalized: List[Tuple[str, str]] = [
        (src, normalize_code(val)) for src, val in candidates if normalize_code(val)
    ]
    if not normalized:
        return "", warnings

    whitelisted = [(src, val) for src, val in normalized if is_whitelisted(val)]
    if whitelisted:
        chosen_src, chosen = whitelisted[0]
        distinct = {val for _, val in whitelisted}
        if len(distinct) > 1:
            detail = "，".join(f"{src}={val}" for src, val in whitelisted)
            warnings.append(
                f"⚠️ 仓库代码多来源不一致（{detail}），已采用「{chosen_src}」的 {chosen}，请人工确认。"
            )
        return chosen, warnings

    # 无白名单命中，退回格式匹配
    formatted = [(src, val) for src, val in normalized if matches_format(val)]
    if formatted:
        chosen_src, chosen = formatted[0]
        warnings.append(
            f"⚠️ 仓库代码 {chosen}（来源：{chosen_src}）不在已知白名单中，可能是新仓或识别有误，请人工确认。"
        )
        return chosen, warnings

    return "", warnings
