"""R12-20：生产代码里不能留下 1021.76。测试文件可以保留这条反例。"""
from __future__ import annotations

from pathlib import Path


def test_production_tree_has_no_magic_total():
    root = Path(__file__).resolve().parents[2]
    needle = "1021" + ".76"
    hits = []
    for path in root.rglob("*.py"):
        if "tests" in path.parts or path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if needle in text:
            hits.append(str(path.relative_to(root)))
    assert hits == []
