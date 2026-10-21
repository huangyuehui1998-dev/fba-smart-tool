"""历史任务编号和历史文件名：拒绝路径穿越，统一返回可判定的 400。"""
from __future__ import annotations

import re
from urllib.parse import unquote

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_FORBIDDEN = ("/", "\\", "\x00", ":")


def _decode(value: str) -> str:
    text = str(value or "")
    return unquote(unquote(text))


def _reject(text: str) -> None:
    if not text or len(text) > 128:
        raise ValueError("任务编号不合法")
    if any(mark in text for mark in _FORBIDDEN) or ".." in text:
        raise ValueError("任务编号不合法")


def safe_history_path(task_id: str) -> str:
    """URL 解码最多两轮，再确认编号不能逃出历史目录。"""
    text = _decode(task_id).strip()
    _reject(text)
    if not _SAFE_ID.fullmatch(text):
        raise ValueError("任务编号不合法")
    from fba_tool.session_store import HISTORY_DIR

    root = HISTORY_DIR.resolve()
    path = (root / f"{text}.json").resolve()
    if path.parent != root:
        raise ValueError("任务编号不合法")
    return text


def safe_history_filename(name: str) -> str:
    """下载文件名使用同一套穿越规则，确认仍在 history 目录内。"""
    text = _decode(name).strip()
    if not text or len(text) > 128:
        raise ValueError("文件名不合法")
    if any(mark in text for mark in _FORBIDDEN) or ".." in text or text.startswith("."):
        raise ValueError("文件名不合法")
    from fba_tool.history_files import history_dir

    root = history_dir().resolve()
    path = (root / text).resolve()
    if path != root and root not in path.parents:
        raise ValueError("文件名不合法")
    return text


def history_task_suffix(raw_path: str) -> str:
    """`/api/tasks/history/<suffix>` 的后缀；列表路由返回空串。"""
    path = raw_path.split("?", 1)[0]
    prefix = "/api/tasks/history/"
    if not path.startswith(prefix):
        return ""
    return path[len(prefix) :]
