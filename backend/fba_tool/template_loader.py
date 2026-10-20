from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import openpyxl

from fba_tool.app_paths import (
    app_data_dir,
    bundled_config_dir,
    bundled_templates_dir,
    ensure_app_data_layout,
    ensure_portable_dirs,
    project_root,
    resolve_config_read,
    runtime_root,
    user_config_dir,
    user_templates_dir,
)

# 向后兼容：CONFIG_DIR / TEMPLATES_DIR 指向 app_data 下的可写目录
APP_ROOT = project_root()
APP_DATA_DIR = app_data_dir()
CONFIG_DIR = user_config_dir()
TEMPLATES_DIR = user_templates_dir()


def app_root() -> Path:
    return project_root()


def templates_dir() -> Path:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    return TEMPLATES_DIR


def _template_search_dirs() -> tuple[Path, ...]:
    return (user_templates_dir(), bundled_templates_dir())


def find_template(*keywords: str) -> Path | None:
    if not keywords:
        return None
    for td in _template_search_dirs():
        if not td.exists():
            continue
        files = sorted(td.glob("*.xlsx"))
        for f in files:
            if all(k.lower() in f.name.lower() for k in keywords):
                return f
        for f in files:
            if any(k.lower() in f.name.lower() for k in keywords):
                return f
    return None


def template_path(name: str) -> Path | None:
    for td in _template_search_dirs():
        direct = td / name
        if direct.exists():
            return direct
    return find_template(name.replace(".xlsx", ""))


def load_sku_mapping() -> Dict[str, str]:
    path = resolve_config_read("sku_mapping.json")
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()}
    except Exception:
        return {}


def list_user_templates() -> list[str]:
    td = user_templates_dir()
    if not td.exists():
        return []
    return sorted([p.name for p in td.iterdir() if p.suffix.lower() in {".xlsx", ".xls", ".csv"}])


def read_template_headers(name: str, max_rows: int = 6) -> list[list]:
    path = template_path(name) or find_template(name)
    if path is None:
        return []
    suffix = path.suffix.lower()
    if suffix == ".csv":
        import csv

        rows: list[list] = []
        with path.open(encoding="utf-8-sig", newline="") as fh:
            for i, row in enumerate(csv.reader(fh)):
                if i >= max_rows:
                    break
                rows.append(["" if c is None else c for c in row])
        return rows
    if suffix == ".xls":
        import pandas as pd

        df = pd.read_excel(path, nrows=max_rows, header=None)
        return [["" if pd.isna(c) else c for c in row] for row in df.values.tolist()]

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i >= max_rows:
            break
        rows.append(["" if c is None else c for c in row])
    wb.close()
    return rows


__all__ = [
    "APP_DATA_DIR",
    "APP_ROOT",
    "CONFIG_DIR",
    "TEMPLATES_DIR",
    "app_root",
    "bundled_config_dir",
    "bundled_templates_dir",
    "ensure_app_data_layout",
    "ensure_portable_dirs",
    "find_template",
    "list_user_templates",
    "load_sku_mapping",
    "project_root",
    "read_template_headers",
    "runtime_root",
    "template_path",
    "templates_dir",
    "user_config_dir",
    "user_templates_dir",
]
