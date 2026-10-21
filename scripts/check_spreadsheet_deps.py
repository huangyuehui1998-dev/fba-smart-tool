"""A7：生产代码不得用浏览器解析货代 xlsx，也不得依赖有漏洞的 SheetJS 0.18.5。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (
    "@corbe30/fortune-excel",
    "@fortune-sheet/core",
    "@fortune-sheet/react",
    "@fortune-sheet",
    "@zwight/luckyexcel",
    "luckyexcel",
    "fortune-excel",
    "LuckyExcel",
    "transformExcelToFortune",
    "transformExcelToLucky",
)
SCAN_ROOTS = (ROOT / "frontend" / "src", ROOT / "backend", ROOT / "scripts")
SKIP_NAMES = {"check_spreadsheet_deps.py"}


def problems() -> list[str]:
    found: list[str] = []
    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    for name in deps:
        if name.startswith("@fortune-sheet") or name in {"@corbe30/fortune-excel", "@zwight/luckyexcel", "luckyexcel"}:
            found.append(f"package.json 仍依赖 {name}")
    xlsx = deps.get("xlsx", "")
    if "0.18.5" in str(xlsx):
        found.append("package.json 的 xlsx 仍指向 0.18.5")
    lock = ROOT / "frontend" / "package-lock.json"
    if lock.is_file() and '"xlsx"' in lock.read_text(encoding="utf-8") and "0.18.5" in lock.read_text(encoding="utf-8"):
        # 只在 xlsx 包自己的版本字段上失败，避免别的包碰巧写到这个号。
        data = json.loads(lock.read_text(encoding="utf-8"))
        packages = data.get("packages") or {}
        entry = packages.get("node_modules/xlsx") or {}
        if str(entry.get("version") or "") == "0.18.5":
            found.append("package-lock 解析到 xlsx 0.18.5")
    for folder in SCAN_ROOTS:
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if not path.is_file() or path.name in SKIP_NAMES:
                continue
            if path.suffix.lower() not in {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".yml", ".yaml"}:
                continue
            if "node_modules" in path.parts or "dist" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for token in FORBIDDEN:
                if token in text:
                    found.append(f"{path.relative_to(ROOT)} 含有 {token}")
                    break
    return found


def main() -> int:
    found = problems()
    if found:
        print("\n".join(found))
        return 1
    print("spreadsheet dependency check ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
