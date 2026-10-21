"""箱侧冒烟的独立复算。只读原始文件，不导入产品代码。

第 15 批账单与逐箱合计不一致，这里不把「推算账单 = 账单」写成断言。
pending_verification 的尺寸叠加读法也不在这里给出红绿结论。
"""
from __future__ import annotations

import os
from pathlib import Path


def realdata_root() -> Path:
    return Path(os.environ.get("FBA_REALDATA_DIR", "/workspace/fba_tool/realdata"))


def available() -> bool:
    root = realdata_root()
    if not root.is_dir():
        return False
    return any(root.iterdir())
