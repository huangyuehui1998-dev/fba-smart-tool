#!/usr/bin/env python3
"""将 frontend/dist/client 同步到 backend/dist，供 FastAPI 与 PyInstaller 打包使用。"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend" / "dist" / "client"
DEST = ROOT / "backend" / "dist"


def _pick_client_entry(assets: Path, shell_text: str = "") -> str:
    if shell_text:
        match = re.search(r'src:"/assets/([^"]+\.js)"', shell_text)
        if match:
            candidate = assets / match.group(1)
            if candidate.is_file():
                return match.group(1)
        match = re.search(
            r'<script type="module"[^>]*src="/assets/([^"]+\.js)"',
            shell_text,
        )
        if match:
            candidate = assets / match.group(1)
            if candidate.is_file():
                return match.group(1)

    index_entries = [
        p.name
        for p in assets.glob("index-*.js")
        if p.is_file() and not p.name.startswith("index.esm")
    ]
    if index_entries:
        return max(
            (assets / n for n in index_entries),
            key=lambda p: p.stat().st_size,
        ).name

    main_js = sorted(assets.glob("main-*.js"))
    if main_js:
        return main_js[0].name

    raise FileNotFoundError("assets/ 中未找到 TanStack 客户端入口 JS")


def _extract_tsr_script(fragment: str) -> str:
    fragment = fragment.replace("\x00", "")
    match = re.search(
        r'<script[^>]*>\(self\.\$R=self\.\$R\|\|\{\}\)\["tsr"\].*?</script>',
        fragment,
        re.DOTALL,
    )
    if not match:
        raise ValueError("_shell.html 缺少 $_TSR 引导脚本")
    script = match.group(0)
    script = script.replace("ssr:!0", "ssr:!1").replace("ssr:true", "ssr:false")
    script = re.sub(
        r"matches:\$R\[\d+\]=\[\$R\[\d+\]=\{[^]]+\}\]",
        "matches:[]",
        script,
        count=1,
    )
    return script


def _build_index_html(dest: Path, shell: Path) -> None:
    """TanStack SPA 预渲染产出的是 HTML 片段，需包装为完整文档。"""
    fragment = shell.read_text(encoding="utf-8")
    assets = dest / "assets"
    entry = _pick_client_entry(assets, fragment)
    tsr_script = _extract_tsr_script(fragment)

    css_files = sorted(assets.glob("*.css"))
    css_links = "\n".join(
        f'    <link rel="stylesheet" href="/assets/{p.name}" />' for p in css_files
    )
    preload_names = [entry]
    for pattern in ("index-*.js", "use-prevent-browser-file-drop-*.js"):
        for p in sorted(assets.glob(pattern)):
            if p.name not in preload_names and not p.name.startswith("index.esm"):
                preload_names.append(p.name)
    preloads = "\n".join(
        f'    <link rel="modulepreload" href="/assets/{name}" />' for name in preload_names
    )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>FBA Smart Tool</title>
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
{css_links}
{preloads}
  </head>
  <body>
    <div id="root"></div>
    {tsr_script}
    <script type="module" async crossorigin src="/assets/{entry}"></script>
  </body>
</html>
"""
    (dest / "index.html").write_text(html, encoding="utf-8")


def _fix_vite_chunk_paths(dest: Path) -> None:
    """Vite mapDeps 预加载会对路径执行 `"/" + path`（GR 函数）。

    因此 mapDeps 数组里必须是 assets/xxx（无 leading slash）。
    若写成 /assets/xxx 会变成 //assets/xxx → ERR_NAME_NOT_RESOLVED。
    """
    assets = dest / "assets"
    if not assets.is_dir():
        return
    for js in assets.glob("*.js"):
        text = js.read_text(encoding="utf-8")
        if "__vite__mapDeps" not in text:
            continue
        lines = text.split("\n", 1)
        header = lines[0]
        if not header.startswith("const __vite__mapDeps"):
            continue
        patched_header = header.replace('"/assets/', '"assets/').replace("'/assets/", "'assets/")
        if patched_header == header:
            continue
        lines[0] = patched_header
        js.write_text("\n".join(lines), encoding="utf-8")


def _ensure_index_html(dest: Path) -> None:
    """Vite SPA 直接产出带 #root 的 index.html。旧的 _shell.html 仍可包一层。"""
    index = dest / "index.html"
    if index.is_file() and 'id="root"' in index.read_text(encoding="utf-8", errors="replace"):
        return
    shell = dest / "_shell.html"
    if shell.is_file():
        raw = shell.read_text(encoding="utf-8", errors="surrogateescape").replace("\x00", "")
        shell.write_text(raw, encoding="utf-8")
        _build_index_html(dest, shell)
        return
    raise FileNotFoundError("未找到带 #root 的 index.html，请先 npm run build")


def _sync_tree_inplace(src: Path, dest: Path) -> None:
    """就地覆盖同步，避免 Windows 下 rmtree 整个 assets 目录时被占用锁失败。"""
    dest.mkdir(parents=True, exist_ok=True)
    src_files: set[Path] = set()
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        target = dest / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        src_files.add(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)

    for item in dest.rglob("*"):
        if not item.is_file():
            continue
        if item.relative_to(dest) not in src_files:
            try:
                item.unlink()
            except OSError:
                pass

    for directory in sorted(
        (p for p in dest.rglob("*") if p.is_dir()),
        key=lambda p: len(p.parts),
        reverse=True,
    ):
        try:
            if not any(directory.iterdir()):
                directory.rmdir()
        except OSError:
            pass


def _replace_dest_dir(src: Path, dest: Path) -> None:
    """优先整目录替换；若 dist 被占用则退化为就地覆盖。"""
    if not dest.exists():
        shutil.copytree(src, dest)
        return
    try:
        shutil.rmtree(dest)
        shutil.copytree(src, dest)
    except PermissionError:
        _sync_tree_inplace(src, dest)


def main() -> int:
    if not SRC.is_dir():
        print(f"错误：未找到 {SRC}", file=sys.stderr)
        print("请先执行：cd frontend && npm run build", file=sys.stderr)
        return 1

    if not any(SRC.iterdir()):
        print(f"错误：{SRC} 为空，请先 npm run build", file=sys.stderr)
        return 1

    _replace_dest_dir(SRC, DEST)

    favicon_src = ROOT / "frontend" / "public" / "favicon.svg"
    if favicon_src.is_file():
        shutil.copy2(favicon_src, DEST / "favicon.svg")

    try:
        _ensure_index_html(DEST)
        _fix_vite_chunk_paths(DEST)
    except (FileNotFoundError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    index = DEST / "index.html"
    content = index.read_text(encoding="utf-8")
    if "ssr:!0" in content or "ssr:true" in content:
        print("错误：index.html 仍含 ssr:true", file=sys.stderr)
        return 1
    if 'id="root"' not in content:
        print("错误：index.html 缺少 #root", file=sys.stderr)
        return 1

    print(f"已同步 {SRC} -> {DEST}")
    print(f"入口页：{index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
