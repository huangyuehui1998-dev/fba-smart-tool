"""发布前校验 backend/dist 静态资源（防止 //assets/、缺失 $_TSR 等历史问题）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "backend" / "dist"
errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def check_index_html() -> None:
    index = DIST / "index.html"
    if not index.is_file():
        fail("缺少 backend/dist/index.html")
        return
    text = index.read_text(encoding="utf-8")
    for token in ("$_TSR", '<div id="root">', "favicon.svg", "FBA Smart Tool"):
        if token not in text:
            fail(f"index.html 缺少 {token!r}")
    if "ssr:!0" in text or "ssr:true" in text:
        fail("index.html 仍含 ssr:true")
    if "matches:[]" not in text and "matches:$R" in text:
        fail("index.html 的 $_TSR matches 未清空为 []")


def check_mapdeps() -> None:
    assets = DIST / "assets"
    if not assets.is_dir():
        fail("缺少 backend/dist/assets")
        return
    checked = 0
    for js in assets.glob("*.js"):
        first = js.read_text(encoding="utf-8").split("\n", 1)[0]
        if not first.startswith("const __vite__mapDeps"):
            continue
        checked += 1
        if '"/assets/' in first or "'/assets/" in first:
            fail(f"{js.name} mapDeps 含 /assets/ 前缀，会导致 //assets/ 404")
        if '"assets/' not in first and "'assets/" not in first:
            fail(f"{js.name} mapDeps 未找到 assets/ 相对路径")
    if checked == 0:
        fail("未找到任何 __vite__mapDeps 行")


def check_favicon() -> None:
    if not (DIST / "favicon.svg").is_file():
        fail("缺少 backend/dist/favicon.svg")


def check_client_entry() -> None:
    index = DIST / "index.html"
    if not index.is_file():
        return
    text = index.read_text(encoding="utf-8")
    match = re.search(r'src="/assets/(index-[^"]+\.js)"', text)
    if not match:
        fail("index.html 未引用 /assets/index-*.js 入口")
        return
    entry_name = match.group(1)
    entry_js = DIST / "assets" / entry_name
    if not entry_js.is_file():
        fail(f"index.html 引用的入口不存在：{entry_name}")
        return
    body = entry_js.read_text(encoding="utf-8")
    if "createRoot" not in body:
        fail(f"{entry_name} 未包含 createRoot（可能回退到 hydrateRoot）")
    if "hydrateRoot(document" in body:
        fail(f"{entry_name} 仍对 document 调用 hydrateRoot，水合不匹配会导致白屏")


def check_forbidden_listing_files() -> None:
    import sys

    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "packaging"))
    from release_manifest import forbidden_real_hits

    hits = forbidden_real_hits(root)
    if hits:
        fail("仓库里有禁止提交的领星售价表：" + ", ".join(hits))


def main() -> int:
    check_forbidden_listing_files()
    check_index_html()
    check_mapdeps()
    check_favicon()
    check_client_entry()
    if errors:
        print("发布校验失败：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("发布校验通过：index.html / $_TSR / mapDeps / favicon / createRoot")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
