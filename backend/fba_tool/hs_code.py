"""S8：HS 编码格式校验（D5）。

依据：
- 中国海关《进出口税则》：税则号列 8 位，报关单“商品编号”填 10 位（8 位税号 + 2 位附加码）。
- 美国 HTSUS（USITC）：8 位税目 + 2 位统计后缀 = 10 位。
所以只接受 8 位或 10 位数字；允许用户输入时带点、空格或横线（如 9507.10.00.00），保存时去掉。
"""
from __future__ import annotations

import re
from typing import Any, Optional

_STRIP = re.compile(r"[\s.\-·]")


class HsCodeError(ValueError):
    pass


def normalize_hs_code(value: Any, *, field_label: str = "HS 编码") -> Optional[str]:
    """空值返回 None（表示清空）；合法返回纯数字；不合法抛 HsCodeError。"""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    import unicodedata

    # 全角数字/点（中文输入法常见）先转半角；之后只认 ASCII 0-9（isdigit 会放过阿拉伯数字等其他文字的数字）
    s = _STRIP.sub("", unicodedata.normalize("NFKC", str(value)).strip())
    if not s:
        return None
    if not re.fullmatch(r"[0-9]+", s):
        raise HsCodeError(f"{field_label}「{value}」格式不对：只能是数字（可带点或空格分隔），例如 9507100000")
    if len(s) not in (8, 10):
        raise HsCodeError(f"{field_label}「{value}」应为 8 位或 10 位数字（中国报关商品编号 10 位，美国 HTS 10 位），现在是 {len(s)} 位")
    return s


def is_valid_hs_code(value: Any) -> bool:
    try:
        return normalize_hs_code(value) is not None
    except HsCodeError:
        return False
