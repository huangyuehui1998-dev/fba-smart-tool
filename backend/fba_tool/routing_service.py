"""刷仓文件名里的仓库代码和票序。路由层只负责 HTTP。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from loguru import logger

from fba_tool.warehouse_codes import known_warehouse_codes

BLACKLIST_TOKENS: frozenset[str] = frozenset(
    {"BOX", "SKU", "CTN", "QTY", "PCS", "UNIT", "AMZN", "TEST", "PART", "PACK", "ITEM", "DOC", "TAB", "FBA"}
)

WIN_RESERVED_NAMES: frozenset[str] = frozenset(
    {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
     "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}
)


def sanitize_filename(filename: str) -> str:
    """输入安全净化：剔除空字节、路径穿越、控制字符及 Windows 保留设备名。"""
    if not filename:
        return "UNKNOWN.csv"
    # 剔除空字节与控制字符
    cleaned = filename.replace("\x00", "")
    cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", cleaned)
    # 剥离多层目录穿越与 Windows/Unix 路径分隔符
    name = Path(cleaned.replace("\\", "/")).name
    if not name or name in (".", ".."):
        return "UNKNOWN.csv"
    # Windows 保留设备名防范
    stem = Path(name).stem.upper()
    if stem in WIN_RESERVED_NAMES:
        return f"safe_{name}"
    return name


def extract_warehouse_from_filename(filename: str) -> str:
    """从文件名提取仓库代码，例如：第一票ONT8.csv -> ONT8"""
    code = strict_warehouse_from_filename(filename)
    if code:
        return code
    m = re.search(r"([A-Z]{3}\d+)", (filename or "").upper())
    if m:
        return m.group(1)
    m2 = re.search(r"([a-zA-Z0-9]+)\.csv$", filename or "", re.IGNORECASE)
    if m2:
        return m2.group(1).upper()
    return "UNKNOWN"


def strict_warehouse_from_filename(filename: str) -> str:
    """只认真实合法的 FBA 仓库代码片段（3 个字母 + 1~2 位数字，且必须在白名单内）；

    排除黑名单单词（如 BOX1、CTN2、SKU1 等）及未收录的代码。
    """
    clean_name = sanitize_filename(filename)
    stem = Path(clean_name).stem.upper()
    # 查找符合 3字母+1-2数字 的所有候选片段
    matches = re.findall(r"(?<![A-Z0-9])([A-Z]{3}\d{1,2})(?![A-Z0-9])", stem)
    known = known_warehouse_codes()
    for token in matches:
        if token in BLACKLIST_TOKENS:
            continue
        if token in known:
            return token
    return ""


def resolve_routing_warehouse(
    csv_code: str,
    filename: str,
    is_routing_mode: bool = False,
) -> tuple[str, str, Optional[str]]:
    """仓库代码仲裁判定。

    参数:
    - csv_code: CSV 内部记录的仓库代码
    - filename: 上传的文件名
    - is_routing_mode: 是否为货代刷仓模式。
      * 当 is_routing_mode=False (默认): CSV 仓库严格优先，文件名仅作兜底，保证历史单票验证 100% 兼容。
      * 当 is_routing_mode=True: 货代刷仓模式，合法的文件名仓库优先覆盖旧 CSV 模板残留仓库。

    返回 (仓库代码, 来源, 警告或 None)。
    """
    clean_fn = sanitize_filename(filename)
    csv_code = (csv_code or "").strip().upper()
    if csv_code in ("", "UNKN", "UNKNOWN"):
        csv_code = ""

    fn_code = strict_warehouse_from_filename(clean_fn)

    if is_routing_mode:
        if fn_code:
            warn = None
            if csv_code and fn_code != csv_code:
                warn = (
                    f"{clean_fn}：刷仓模式优先采用文件名仓库 {fn_code}（覆盖原 CSV 中的 {csv_code}），请核对"
                )
                logger.info(
                    f"AUDIT: WH_OVERRIDE filename={clean_fn} old_csv={csv_code} final_wh={fn_code}"
                )
            return fn_code, "文件名", warn
        if csv_code:
            return csv_code, "CSV", None
        return "UNKN", "", f"{clean_fn}：CSV 和文件名里都没有仓库代码，仓库列为 UNKN，请在 CSV 或文件名里补上"

    # 历史默认模式 (is_routing_mode=False): CSV 优先
    if csv_code:
        warn = None
        if fn_code and fn_code != csv_code:
            warn = (
                f"{clean_fn}：文件名里的仓库代码 {fn_code} 和 CSV 里的 {csv_code} 不一致，"
                f"已按 CSV 用 {csv_code}，请核对"
            )
        return csv_code, "CSV", warn
    if fn_code:
        return fn_code, "文件名", f"{clean_fn}：CSV 里没有仓库代码，按文件名用 {fn_code}，请核对"
    return "UNKN", "", f"{clean_fn}：CSV 和文件名里都没有仓库代码，仓库列为 UNKN，请在 CSV 或文件名里补上"


def extract_ticket_rank(filename: str) -> int:
    """从文件名提取票数排序（第一票 -> 1, 第二票 -> 2）"""
    clean_fn = sanitize_filename(filename)
    mapping = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    m = re.search(r"第([一二三四五六七八九十\d]+)票", clean_fn)
    if m:
        val = m.group(1)
        if val.isdigit():
            return int(val)
        return mapping.get(val, 999)
    return 999
