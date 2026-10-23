#!/usr/bin/env pwsh
# FBA Smart Tool - standalone build (frontend + sync + PyInstaller onedir)
$ErrorActionPreference = "Stop"
# PowerShell 7 可能把原生程序写到 stderr 当成失败。npm 的警告不应中断打包。
$PSNativeCommandUseErrorActionPreference = $false
# 保证 Python 用 UTF-8 读写文件名和日志。Windows 上路径本身走 UTF-16 API。
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
try { Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force } catch { }

$Root = Split-Path -Parent $PSScriptRoot
$VenvPy = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) { throw "backend\.venv not found. Create it with Python 3.12 before packaging." }

# npm.ps1 在默认执行策略下会报错；CI 和本机都优先用 npm.cmd。
$NpmCmd = "npm"
$NpmCmdInfo = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($NpmCmdInfo) { $NpmCmd = $NpmCmdInfo.Source }

Write-Host "==> 0/5 generate bundled assets (qiluo template)" -ForegroundColor Cyan
& $VenvPy (Join-Path $Root "scripts\generate_qiluo_template.py")
if ($LASTEXITCODE -ne 0) { throw "generate_qiluo_template failed" }

Write-Host "==> 1/5 frontend npm run build" -ForegroundColor Cyan
Push-Location (Join-Path $Root "frontend")
& $NpmCmd run build
if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
Pop-Location

Write-Host "==> 2/5 sync frontend -> backend/dist" -ForegroundColor Cyan
& $VenvPy (Join-Path $Root "scripts\sync_frontend_static.py")
if ($LASTEXITCODE -ne 0) { throw "sync_frontend_static failed" }

Write-Host "==> 3/5 verify release dist + bundled resources" -ForegroundColor Cyan
& $VenvPy (Join-Path $Root "scripts\verify_release_dist.py")
if ($LASTEXITCODE -ne 0) { throw "verify_release_dist failed" }
& $VenvPy (Join-Path $Root "scripts\verify_bundled_resources.py")
if ($LASTEXITCODE -ne 0) { throw "verify_bundled_resources failed" }

Write-Host "==> 4/5 refuse to pack over app_data, then PyInstaller onedir" -ForegroundColor Cyan
& $VenvPy (Join-Path $Root "scripts\release_guard.py") (Join-Path $Root "dist")
if ($LASTEXITCODE -ne 0) { throw "dist 里已有用户数据，已停止打包" }
# 版本与 backend/requirements-dev.lock.txt 里的打包钉死一致，避免 CI 装到不兼容的最新版。
& $VenvPy -m pip install -r (Join-Path $Root "packaging\requirements-pyinstaller.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed" }
& $VenvPy -c "import sys; print('python', sys.version)"
& $VenvPy -m PyInstaller --version
if ($LASTEXITCODE -ne 0) { throw "pyinstaller --version failed" }
& $VenvPy -m PyInstaller (Join-Path $Root "packaging\FBA_Smart_Tool.spec") --noconfirm --clean --distpath (Join-Path $Root "dist") --workpath (Join-Path $Root "build\pyinstaller")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$outDir = Join-Path $Root "dist\FBA_Smart_Tool"
& $VenvPy (Join-Path $Root "scripts\finish_portable_dist.py")
if ($LASTEXITCODE -ne 0) { throw "finish_portable_dist failed" }

$versionFile = Join-Path $Root "backend\fba_tool\app_version.py"
$versionText = Get-Content -Raw -Encoding UTF8 $versionFile
if ($versionText -notmatch 'APP_VERSION = "([^"]+)"') { throw "APP_VERSION missing in app_version.py" }
$AppVersion = $Matches[1]
Write-Host ""
Write-Host "Done. Distribute folder:" (Join-Path $Root "dist\FBA_Smart_Tool_${AppVersion}_便携版") -ForegroundColor Green
Write-Host "Zip:" (Join-Path $Root "dist\FBA_Smart_Tool_${AppVersion}_便携版.zip") -ForegroundColor Green
Write-Host "Launcher:" (Join-Path $Root "dist\FBA_Smart_Tool_${AppVersion}_便携版\FBA_Smart_Tool\启动FBA工具.bat") -ForegroundColor Green
