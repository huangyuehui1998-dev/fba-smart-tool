# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas = [
    ('main.py', '.'),
    ('settings.py', '.'),
    ('routers', 'routers'),
    ('services', 'services'),
    ('schemas', 'schemas'),
    ('fba_tool', 'fba_tool'),
    ('config', 'config'),
    ('templates', 'templates'),
    ('dist', 'dist'),
]
binaries = []
hiddenimports = ['uvicorn', 'fastapi', 'starlette', 'pandas', 'openpyxl', 'pdfplumber', 'requests']

for pkg in ['pandas', 'openpyxl', 'pdfplumber', 'requests', 'fastapi', 'starlette', 'uvicorn']:
    tmp = collect_all(pkg)
    datas += tmp[0]
    binaries += tmp[1]
    hiddenimports += tmp[2]

a = Analysis(
    ['launcher_fastapi.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FBAWizard_V1.8',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FBAWizard_V1.8',
)
