"""补全便携版 dist 目录：使用说明 + 启动脚本，并打 zip。

模板和出厂配置必须已经由 PyInstaller 收进 _internal。这里只验收，不补拷贝。
zip 内的中文文件名使用 UTF-8 标志（EFS）。不要在 Linux 上解压后再打包。
"""
from __future__ import annotations

import hashlib
import shutil
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from fba_tool.app_version import APP_VERSION as RELEASE_VERSION  # noqa: E402

OUT = ROOT / "dist" / "FBA_Smart_Tool"
PORTABLE_NAME = f"FBA_Smart_Tool_{RELEASE_VERSION}_便携版"
ZIP_PREFIX = "FBA_Smart_Tool"
LAUNCHER_NAME = "启动FBA工具.bat"
README_NAME = "使用说明.txt"
UTF8_NAME_FLAG = 0x800
SKIP_DIR_NAMES = {"app_data", "__pycache__"}
_OUR_TREES = {"config", "templates"}
_FORBIDDEN_BASENAMES = {
    "lingxing.json",
    "invoice_history.json",
    "invoice_history.default.json",
    ".env",
}


def _should_skip(path: Path, out_dir: Path) -> bool:
    rel_parts = path.relative_to(out_dir).parts
    if any(part in SKIP_DIR_NAMES for part in rel_parts):
        return True
    return path.suffix.lower() == ".pyc"


def _packaging_manifest():
    packaging = str(ROOT / "packaging")
    if packaging not in sys.path:
        sys.path.insert(0, packaging)
    from release_manifest import bundle_relpaths

    return bundle_relpaths


def expected_internal_files(out_dir: Path) -> list[Path]:
    bundle_relpaths = _packaging_manifest()
    paths = [out_dir / "_internal" / Path(rel) for rel in bundle_relpaths(ROOT)]
    paths.append(out_dir / "_internal" / "dist" / "index.html")
    return paths


def missing_internal_files(out_dir: Path) -> list[str]:
    missing: list[str] = []
    for path in expected_internal_files(out_dir):
        if not path.is_file() or path.stat().st_size <= 0:
            missing.append(path.relative_to(out_dir).as_posix())
    return missing


def _zip_info(path: Path, arcname: str) -> zipfile.ZipInfo:
    st = path.stat()
    stamp = time.localtime(st.st_mtime)[:6]
    if stamp[0] < 1980:
        stamp = (1980, 1, 1, 0, 0, 0)
    info = zipfile.ZipInfo(filename=arcname, date_time=stamp)
    info.compress_type = zipfile.ZIP_DEFLATED
    # 写条目时 zipfile 会清掉 flag_bits，再对非 ASCII 名字写上 UTF-8 标志。
    # 这里先标上；verify_portable_zip 读回中央目录，标志丢了就失败。
    info.flag_bits |= UTF8_NAME_FLAG
    info.external_attr = (st.st_mode & 0xFFFF) << 16
    return info


def write_utf8_zip(out_dir: Path, zip_path: Path, prefix: str = ZIP_PREFIX) -> None:
    """把 onedir 目录打成 zip。arcname 只用正斜杠，并强制 UTF-8 文件名。"""
    if zip_path.is_file():
        zip_path.unlink()
    files = [path for path in out_dir.rglob("*") if path.is_file() and not _should_skip(path, out_dir)]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(files):
            arcname = prefix + "/" + path.relative_to(out_dir).as_posix()
            if "\\" in arcname or arcname.startswith("/") or "/../" in f"/{arcname}/":
                raise SystemExit(f"zip 路径不合法：{arcname}")
            info = _zip_info(path, arcname)
            with path.open("rb") as src, zf.open(info, "w") as dest:
                shutil.copyfileobj(src, dest, 1024 * 64)


def _forbidden_member(name: str) -> bool:
    parts = [part for part in name.split("/") if part]
    if any(part in {".git", "app_data", "realdata"} for part in parts):
        return True
    if len(parts) < 2:
        return False
    base = parts[-1]
    in_our_tree = len(parts) >= 3 and parts[1] == "_internal" and parts[2] in _OUR_TREES
    at_package_root = len(parts) == 2
    if "sessions" in parts[1:] and (in_our_tree or parts[1] == "sessions"):
        return True
    if not (in_our_tree or at_package_root):
        return False
    lowered = base.lower()
    if base in _FORBIDDEN_BASENAMES or lowered in _FORBIDDEN_BASENAMES:
        return True
    return lowered.endswith((".db", ".sqlite", ".sqlite3"))


def verify_portable_zip(zip_path: Path, required: list[str]) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if any("\\" in name for name in names):
            raise SystemExit("zip 条目含反斜杠，解压会拆错目录")
        missing = [name for name in required if name not in names]
        if missing:
            raise SystemExit("便携版 zip 缺少：" + ", ".join(missing))
        bad_flags = []
        forbidden = []
        for info in zf.infolist():
            if info.is_dir():
                continue
            if any(ord(ch) > 127 for ch in info.filename) and not (info.flag_bits & UTF8_NAME_FLAG):
                bad_flags.append(info.filename)
            if _forbidden_member(info.filename):
                forbidden.append(info.filename)
        if bad_flags:
            raise SystemExit("中文文件名未设置 UTF-8 标志：" + ", ".join(bad_flags))
        if forbidden:
            raise SystemExit("zip 含禁止发布的文件：" + ", ".join(forbidden))


def _required_zip_members() -> list[str]:
    members = [
        f"{ZIP_PREFIX}/FBA_Smart_Tool.exe",
        f"{ZIP_PREFIX}/{LAUNCHER_NAME}",
        f"{ZIP_PREFIX}/{README_NAME}",
    ]
    for path in expected_internal_files(OUT):
        members.append(ZIP_PREFIX + "/" + path.relative_to(OUT).as_posix())
    return members


def _write_launcher(out_dir: Path) -> None:
    # 启动脚本全部使用 ASCII 字符，避免 .bat 自身因编码导致乱码；
    # chcp 65001 + PYTHONUTF8/PYTHONIOENCODING 双保险，确保控制台中文不乱码。
    (out_dir / LAUNCHER_NAME).write_text(
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        'cd /d "%~dp0"\r\n'
        'set "PYTHONUTF8=1"\r\n'
        'set "PYTHONIOENCODING=utf-8"\r\n'
        'start "" "%~dp0FBA_Smart_Tool.exe"\r\n',
        encoding="ascii",
    )


def main() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from release_guard import refuse_user_data

    refuse_user_data(ROOT / "dist")
    refuse_user_data(OUT)
    if not (OUT / "FBA_Smart_Tool.exe").is_file():
        raise SystemExit(f"未找到 {OUT / 'FBA_Smart_Tool.exe'}，请先运行 build_standalone.ps1")

    missing = missing_internal_files(OUT)
    if missing:
        raise SystemExit(
            "便携版 _internal 缺少白名单资源。PyInstaller 没有收集这些文件；"
            "不要手工拷进 dist，请修 packaging/FBA_Smart_Tool.spec 或 release_manifest.py 后重新打包："
            + ", ".join(missing)
        )

    readme_src = ROOT / "packaging" / "使用说明.txt"
    if not readme_src.is_file():
        readme_src = ROOT / "docs" / "使用说明.md"
    shutil.copy2(readme_src, OUT / README_NAME)

    workflow_doc = ROOT / "FBA_Smart_Tool_工作流与运行逻辑.txt"
    if workflow_doc.is_file():
        shutil.copy2(workflow_doc, OUT / "工作流与运行逻辑.txt")
    else:
        legacy = ROOT / "packaging" / "工作流与运行逻辑_V1.2.txt"
        if legacy.is_file():
            shutil.copy2(legacy, OUT / "工作流与运行逻辑.txt")

    _write_launcher(OUT)

    zip_path = ROOT / "dist" / f"{PORTABLE_NAME}.zip"
    write_utf8_zip(OUT, zip_path)
    verify_portable_zip(zip_path, _required_zip_members())

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

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    mb = zip_path.stat().st_size / 1024 / 1024
    print(f"便携版目录: {folder_path}")
    print(f"运行目录: {dest}")
    print(f"版本: {RELEASE_VERSION}")
    print(f"压缩包: {zip_path} ({mb:.1f} MB)")
    print(f"SHA256: {digest}")
    print("zip UTF-8 文件名校验通过")


if __name__ == "__main__":
    main()
