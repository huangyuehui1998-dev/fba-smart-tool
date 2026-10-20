"""补全便携版 dist 目录：使用说明 + 启动脚本，并打 zip。"""
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from fba_tool.app_version import APP_VERSION as RELEASE_VERSION  # noqa: E402
OUT = ROOT / "dist" / "FBA_Smart_Tool"
PORTABLE_NAME = f"FBA_Smart_Tool_{RELEASE_VERSION}_便携版"
SKIP_DIR_NAMES = {"app_data", "__pycache__"}


def _should_skip(path: Path) -> bool:
    rel_parts = path.relative_to(OUT).parts
    return any(part in SKIP_DIR_NAMES for part in rel_parts)


def main() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from release_guard import refuse_user_data

    refuse_user_data(ROOT / "dist")
    refuse_user_data(OUT)
    if not (OUT / "FBA_Smart_Tool.exe").is_file():
        raise SystemExit(f"未找到 {OUT / 'FBA_Smart_Tool.exe'}，请先运行 build_standalone.ps1")

    required = [
        OUT / "_internal" / "templates" / "forwarders" / "qiluo.xlsx",
        OUT / "_internal" / "config" / "forwarders.default.json",
        OUT / "_internal" / "dist" / "index.html",
    ]
    missing = [str(p.relative_to(OUT)) for p in required if not p.is_file()]
    if missing:
        raise SystemExit(f"便携版资源不完整，缺少：{', '.join(missing)}")

    readme_src = ROOT / "packaging" / "使用说明.txt"
    if not readme_src.is_file():
        readme_src = ROOT / "docs" / "使用说明.md"
    shutil.copy2(readme_src, OUT / "使用说明.txt")

    workflow_doc = ROOT / "FBA_Smart_Tool_工作流与运行逻辑.txt"
    if workflow_doc.is_file():
        shutil.copy2(workflow_doc, OUT / "工作流与运行逻辑.txt")
    else:
        legacy = ROOT / "packaging" / "工作流与运行逻辑_V1.2.txt"
        if legacy.is_file():
            shutil.copy2(legacy, OUT / "工作流与运行逻辑.txt")

    # 启动脚本全部使用 ASCII 字符，避免 .bat 自身因编码导致乱码；
    # chcp 65001 + PYTHONUTF8/PYTHONIOENCODING 双保险，确保控制台中文不乱码。
    (OUT / "启动FBA工具.bat").write_text(
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        'cd /d "%~dp0"\r\n'
        'set "PYTHONUTF8=1"\r\n'
        'set "PYTHONIOENCODING=utf-8"\r\n'
        'start "" "%~dp0FBA_Smart_Tool.exe"\r\n',
        encoding="ascii",
    )

    zip_path = ROOT / "dist" / f"{PORTABLE_NAME}.zip"
    if zip_path.is_file():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in OUT.rglob("*"):
            if not path.is_file() or _should_skip(path):
                continue
            zf.write(path, Path("FBA_Smart_Tool") / path.relative_to(OUT))

    folder_path = ROOT / "dist" / PORTABLE_NAME
    if folder_path.exists():
        shutil.rmtree(folder_path)
    dest = folder_path / "FBA_Smart_Tool"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        OUT,
        dest,
        ignore=shutil.ignore_patterns("app_data", "__pycache__", "*.pyc"),
    )

    mb = zip_path.stat().st_size / 1024 / 1024
    print(f"便携版目录: {folder_path}")
    print(f"运行目录: {dest}")
    print(f"版本: {RELEASE_VERSION}")
    print(f"压缩包: {zip_path} ({mb:.1f} MB)")


if __name__ == "__main__":
    main()
