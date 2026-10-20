"""刷仓文件名里的仓库代码和票序。路由层只负责 HTTP。"""
from __future__ import annotations

import re
from typing import Optional


def extract_warehouse_from_filename(filename: str) -> str:
    """从文件名提取仓库代码，例如：第一票ONT8.csv -> ONT8"""
    m = re.search(r"([A-Z]{3}\d+)", filename.upper())
    if m:
        return m.group(1)
    m2 = re.search(r"([a-zA-Z0-9]+)\.csv$", filename, re.IGNORECASE)
    if m2:
        return m2.group(1).upper()
    return "UNKNOWN"


def strict_warehouse_from_filename(filename: str) -> str:
    """只认像仓库代码的片段（3 个字母 + 数字，如 ONT8）；“表1.csv”这类不算。"""
    m = re.search(r"(?<![A-Z])([A-Z]{3}\d{1,2})(?![A-Z0-9])", (filename or "").upper())
    return m.group(1) if m else ""


def resolve_routing_warehouse(csv_code: str, filename: str) -> tuple[str, str, Optional[str]]:
    """CSV 里的仓库代码优先，文件名只做兜底；两者冲突时给警告。

    返回 (仓库代码, 来源, 警告或 None)。
    """
    csv_code = (csv_code or "").strip().upper()
    if csv_code in ("", "UNKN", "UNKNOWN"):
        csv_code = ""
    fn_code = strict_warehouse_from_filename(filename)
    if csv_code:
        warn = None
        if fn_code and fn_code != csv_code:
            warn = (
                f"{filename}：文件名里的仓库代码 {fn_code} 和 CSV 里的 {csv_code} 不一致，"
                f"已按 CSV 用 {csv_code}，请核对"
            )
            return csv_code, "CSV", warn
        return csv_code, "CSV", warn
    if fn_code:
        return fn_code, "文件名", f"{filename}：CSV 里没有仓库代码，按文件名用 {fn_code}，请核对"
    return "UNKN", "", f"{filename}：CSV 和文件名里都没有仓库代码，仓库列为 UNKN，请在 CSV 或文件名里补上"


def extract_ticket_rank(filename: str) -> int:
    """从文件名提取票数排序（第一票 -> 1, 第二票 -> 2）"""
    mapping = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    m = re.search(r"第([一二三四五六七八九十\d]+)票", filename)
    if m:
        val = m.group(1)
        if val.isdigit():
            return int(val)
        return mapping.get(val, 999)
    return 999
