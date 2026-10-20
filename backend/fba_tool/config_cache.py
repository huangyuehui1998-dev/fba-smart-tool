"""配置文件按 mtime 内存缓存，避免重复读盘。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fba_tool.app_paths import bundled_templates_dir, resolve_config_read, user_templates_dir

_json_cache: Dict[str, tuple[float, Any]] = {}


def load_json_cached(relative_name: str, default: Any = None) -> Any:
    path = resolve_config_read(relative_name)
    mtime = path.stat().st_mtime if path.exists() else -1.0
    cached = _json_cache.get(relative_name)
    if cached and cached[0] == mtime:
        return cached[1]
    if not path.exists():
        value = default if default is not None else {}
    else:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            value = default if default is not None else {}
    _json_cache[relative_name] = (mtime, value)
    return value


def template_mtime(name: str) -> float:
    for td in (user_templates_dir(), bundled_templates_dir()):
        path = td / name
        if path.is_file():
            return path.stat().st_mtime
    from fba_tool.template_loader import template_path

    p = template_path(name)
    return p.stat().st_mtime if p and p.exists() else 0.0
