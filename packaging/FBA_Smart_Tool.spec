# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — FBA Smart Tool V4 便携版（目录模式，启动更快）

使用前请先：
  1. cd frontend && npm run build
  2. python scripts/sync_frontend_static.py   # -> backend/dist
  3. pyinstaller packaging/FBA_Smart_Tool.spec  # bundles backend/dist -> _MEIPASS/dist

或：powershell -ExecutionPolicy Bypass -File scripts/build_standalone.ps1
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
BACKEND = ROOT / "backend"

_extra_datas: list = []
_extra_binaries: list = []
_hiddenimports: list[str] = [
    "main",
    "settings",
    "static_ui",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "multipart",
    "python_multipart",
    "pandas",
    "openpyxl",
    "xlrd",
    "xlwt",
    "pyxlsb",
    "pandas.io.excel._xlrd",
    "pandas.io.excel._pyxlsb",
    "pandas.io.excel._openpyxl",
    "pdfplumber",
    "fitz",
    "numpy",
    "scipy",
    "scipy.ndimage",
    "httpx",
    "requests",
    "email_validator",
    "pydantic",
    "pydantic_core",
    "anyio",
    "anyio._backends._asyncio",
    "sniffio",
    "h11",
    "httptools",
    "watchfiles",
]

for _pkg in ("uvicorn", "fastapi", "starlette", "fitz", "scipy", "xlrd", "pyxlsb"):
    try:
        _d, _b, _h = collect_all(_pkg)
        _extra_datas += _d
        _extra_binaries += _b
        _hiddenimports += _h
    except Exception:
        pass

for _pkg in ("fba_tool", "routers", "services"):
    try:
        _hiddenimports += collect_submodules(_pkg)
    except Exception:
        pass

# S9-step5：模板和出厂配置改为白名单（packaging/release_manifest.py）。真实数据原件留在 backend/ 给测试用，
# 打包只用白名单里的纯格式模板和 packaging/release_templates/ 下的 DEMO / 空白版。
import sys as _sys

_sys.path.insert(0, str(Path(SPECPATH).resolve()))
from release_manifest import pyinstaller_datas as _release_datas  # noqa: E402
from release_manifest import assert_collected as _assert_collected  # noqa: E402


a = Analysis(
    [str(ROOT / "run_app.py")],
    pathex=[str(BACKEND)],
    binaries=_extra_binaries,
    datas=[
        (str(BACKEND / "dist"), "dist"),
        *_release_datas(ROOT),
        *_extra_datas,
    ],
    hiddenimports=_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["streamlit", "matplotlib", "tkinter"],
    noarchive=False,
    optimize=0,
)

# 目录模式下数据在 _internal（sys._MEIPASS）。缺模板就停，不要打包后再拷。
_assert_collected(a.datas, ROOT)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FBA_Smart_Tool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    contents_directory="_internal",
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FBA_Smart_Tool",
)
