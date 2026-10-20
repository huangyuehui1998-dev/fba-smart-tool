"""发布目录里不能带用户数据。打包前发现 app_data、数据库或 backups 就停止。"""
from __future__ import annotations

import sys
from pathlib import Path


USER_DIR_NAMES = {"app_data", "backups"}


def find_user_data(root: Path) -> list[str]:
    if not root.exists():
        return []
    hits: list[str] = []
    for path in root.rglob("*"):
        if path.is_dir() and path.name in USER_DIR_NAMES:
            hits.append(path.relative_to(root).as_posix())
        elif path.is_file() and path.suffix.lower() == ".db":
            hits.append(path.relative_to(root).as_posix())
    return hits


def find_carton_data(config_dir: Path) -> list[str]:
    if not config_dir.exists():
        return []
    hits: list[str] = []
    for path in config_dir.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        if path.suffix.lower() == ".db" or "箱规" in name or "carton_spec" in name:
            hits.append(path.relative_to(config_dir).as_posix())
            continue
        if path.suffix.lower() in {".json", ".csv", ".txt"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "carton_spec" in text or ("qty_per_carton" in text and "length_cm" in text):
                hits.append(path.relative_to(config_dir).as_posix())
    return hits


def refuse_user_data(root: Path) -> None:
    hits = find_user_data(root)
    if hits:
        joined = "；".join(hits)
        raise SystemExit(f"发现发布目录里已有用户数据，已停止打包，避免清掉正在使用的数据：{joined}")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("用法: release_guard.py <发布目录>")
        return 2
    root = Path(argv[1])
    try:
        refuse_user_data(root)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 1
    print("发布目录没有 app_data、数据库或 backups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
