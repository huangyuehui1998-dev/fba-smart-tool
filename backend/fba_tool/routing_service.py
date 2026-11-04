"""刷仓文件名里的仓库代码和票序 (工业级高兼容增强版)。路由层只负责 HTTP。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from loguru import logger

from fba_tool.warehouse_codes import known_warehouse_codes

# 常见干扰关键词黑名单 (排除装箱词汇，支持前缀如 BOX1, CTN2)
BLACKLIST_TOKENS: frozenset[str] = frozenset(
    {"BOX", "SKU", "CTN", "QTY", "PCS", "UNIT", "AMZN", "TEST", "PART", "PACK", "ITEM", "DOC", "TAB", "FBA"}
)

WIN_RESERVED_NAMES: frozenset[str] = frozenset(
    {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
     "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}
)

# AWD 4字母官方中转仓 (如 IUSJ, IUSP, IUSF, STAR 等)
AWD_WAREHOUSE_RE = re.compile(r"^IUS[A-Z]$|^XUS[A-Z]$|^STAR$|^KILN$")
WAREHOUSE_FORMAT_RE = re.compile(r"^[A-Z]{3}\d{1,2}$")


def _is_blacklisted(token: str) -> bool:
    """检查 Token 是否属于黑名单词汇（如 BOX, BOX1, CTN, CTN1, SKU 等）。"""
    if token in BLACKLIST_TOKENS:
        return True
    if len(token) >= 3 and token[:3] in BLACKLIST_TOKENS:
        return True
    if len(token) >= 4 and token[:4] in BLACKLIST_TOKENS:
        return True
    return False


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


def strict_warehouse_from_filename(filename: str) -> str:
    """智能仓码识别（分层漏斗）：
    1. 宽松边界提取：允许数字/下划线/中文前缀 (如 1ONT8, 第1票-ONT8, 01_LAX9)；
    2. 黑名单过滤 (排除 BOX/CTN/SKU 等关键词)；
    3. 白名单精确优先 (Tier 1)；
    4. 标准亚马逊格式兜底 (Tier 2: 3字母+1-2数字 或 AWD 仓)，绝不误杀真实新仓！
    """
    clean_name = sanitize_filename(filename)
    stem = Path(clean_name).stem.upper()

    # 允许前面是数字或非英文字母 (兼容 1ONT8, 01_ONT8, 票1ONT8)
    matches = re.findall(r"(?<![A-Z])([A-Z]{3}\d{1,2})(?![A-Z0-9])", stem)
    awd_matches = re.findall(r"(?<![A-Z0-9])(IUS[A-Z]|XUS[A-Z]|STAR|KILN)(?![A-Z0-9])", stem)
    candidates = matches + awd_matches

    known = known_warehouse_codes()

    # Tier 1: 命中白名单的优先确立
    for token in candidates:
        if _is_blacklisted(token):
            continue
        if token in known:
            return token

    # Tier 2: 未收录但符合标准 FBA / AWD 仓码规范的合法代码，100% 放行决胜
    for token in candidates:
        if _is_blacklisted(token):
            continue
        if WAREHOUSE_FORMAT_RE.match(token) or AWD_WAREHOUSE_RE.match(token):
            return token

    return ""


def extract_warehouse_from_filename(filename: str) -> str:
    """从文件名提取仓库代码，例如：第一票ONT8.csv -> ONT8"""
    code = strict_warehouse_from_filename(filename)
    if code:
        return code
    m = re.search(r"([A-Z]{3}\d+)", (filename or "").upper())
    if m and not _is_blacklisted(m.group(1)):
        return m.group(1)
    m2 = re.search(r"([a-zA-Z0-9]+)\.csv$", filename or "", re.IGNORECASE)
    if m2 and not _is_blacklisted(m2.group(1).upper()):
        return m2.group(1).upper()
    return "UNKNOWN"


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
      * 当 is_routing_mode=True: 货代刷仓模式，文件名仓库具有绝对优先决胜权。

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
                warn = f"{clean_fn}：刷仓模式优先采用文件名仓库 {fn_code}（覆盖原 CSV 中的 {csv_code}），请核对"
                logger.info(
                    f"ROUTING_AUDIT: WH_OVERRIDE filename={clean_fn} old_csv={csv_code} final_wh={fn_code}"
                )
            return fn_code, "文件名", warn
        if csv_code:
            return csv_code, "CSV", None
        return "UNKN", "", f"{clean_fn}：未能识别出仓库代码，请在 CSV 或文件名里补上"

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


def _cn_to_int(cn: str) -> int:
    """中文数字转整数（支持 1~99）"""
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if cn.isdigit():
        return int(cn)
    if cn == "十":
        return 10
    if len(cn) == 2 and cn.startswith("十"):
        return 10 + digits.get(cn[1], 0)
    if len(cn) == 2 and cn.endswith("十"):
        return digits.get(cn[0], 1) * 10
    if len(cn) == 3 and cn[1] == "十":
        return digits.get(cn[0], 1) * 10 + digits.get(cn[2], 0)
    return digits.get(cn, 999)


def extract_ticket_rank(filename: str) -> int:
    """全场景票序解析引擎：支持 '第一票'、'第11票'、'1-ONT8'、'01_'、'票1' 等"""
    clean_fn = sanitize_filename(filename)
    stem = Path(clean_fn).stem

    # 1. 匹配标准“第X票 / 第X单 / 第X批”
    m_cn = re.search(r"第([一二三四五六七八九十\d]+)[票单批次]?", stem)
    if m_cn:
        val = m_cn.group(1)
        if val.isdigit():
            return int(val)
        return _cn_to_int(val)

    # 2. 匹配“票1 / 票2”
    m_p = re.search(r"票(\d+)", stem)
    if m_p:
        return int(m_p.group(1))

    # 3. 匹配开头数字前缀，如 "1-ONT8", "02_LAX9", "3.GYR3", "1ONT8"
    m_pre = re.match(r"^(\d+)(?:[\-_.\s]|(?=[A-Za-z]))", stem)
    if m_pre:
        return int(m_pre.group(1))

    return 999
