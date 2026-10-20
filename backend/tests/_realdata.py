"""真实样本门禁。

路径不存在就 skip，原因里固定含「需要 box realdata」。
模块级读取真实样本的测试必须在读文件之前调用 skip_module_if_missing，
否则收集阶段会因 FileNotFoundError 中断。
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence, Union

import pytest

REALDATA_REASON = "需要 box realdata"
PathLike = Union[str, Path]


def _missing(paths: Iterable[PathLike]) -> list[str]:
    missing: list[str] = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            missing.append(str(path))
    return missing


def _reason(missing: Sequence[str]) -> str:
    if not missing:
        return REALDATA_REASON
    return REALDATA_REASON + ": " + ", ".join(missing)


def requires_realdata(*paths: PathLike):
    """装饰单个测试：任一路径不存在则 skip。"""
    missing = _missing(paths)
    return pytest.mark.skipif(bool(missing), reason=_reason(missing))


def skip_module_if_missing(*paths: PathLike) -> None:
    """收集阶段跳过整个模块。"""
    missing = _missing(paths)
    if missing:
        pytest.skip(_reason(missing), allow_module_level=True)
