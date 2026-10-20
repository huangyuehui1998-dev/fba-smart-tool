"""发布前校验 backend 出厂资源（货代模板、配置等）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

REQUIRED = [
    BACKEND / "templates" / "forwarders" / "qiluo.xlsx",
    BACKEND / "templates" / "customs" / "报关资料模板.xlsx",
    BACKEND / "config" / "forwarders.default.json",
    BACKEND / "config" / "exporter_profiles.default.json",
    BACKEND / "dist" / "index.html",
    BACKEND / "dist" / "favicon.svg",
]


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED:
        if not path.is_file():
            errors.append(f"缺少 {path.relative_to(ROOT)}")
    if errors:
        print("出厂资源校验失败：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("出厂资源校验通过：货代模板 / 报关模板 / 出厂配置 / dist/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
