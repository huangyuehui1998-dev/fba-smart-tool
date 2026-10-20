#!/usr/bin/env pwsh
# FBA Smart Tool - standalone build (frontend + sync + PyInstaller onedir)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VenvPy = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) { throw "backend\.venv not found" }

Write-Host "==> 0/5 generate bundled assets (qiluo template)" -ForegroundColor Cyan
& $VenvPy (Join-Path $Root "scripts\generate_qiluo_template.py")
if ($LASTEXITCODE -ne 0) { throw "generate_qiluo_template failed" }

Write-Host "==> 1/5 frontend npm run build" -ForegroundColor Cyan
Push-Location (Join-Path $Root "frontend")
npm run build
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

Write-Host "==> 4/5 PyInstaller onedir" -ForegroundColor Cyan
& $VenvPy -m pip install pyinstaller --quiet
& $VenvPy -m PyInstaller (Join-Path $Root "packaging\FBA_Smart_Tool.spec") --noconfirm --distpath (Join-Path $Root "dist") --workpath (Join-Path $Root "build\pyinstaller")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$outDir = Join-Path $Root "dist\FBA_Smart_Tool"
& $VenvPy (Join-Path $Root "scripts\finish_portable_dist.py")
if ($LASTEXITCODE -ne 0) { throw "finish_portable_dist failed" }

Write-Host ""
Write-Host "Done. Distribute folder:" (Join-Path $Root "dist\FBA_Smart_Tool_V3.2_便携版") -ForegroundColor Green
Write-Host "Zip:" (Join-Path $Root "dist\FBA_Smart_Tool_V3.2_便携版.zip") -ForegroundColor Green
Write-Host "Launcher:" (Join-Path $Root "dist\FBA_Smart_Tool_V3.2_便携版\FBA_Smart_Tool\启动FBA工具.bat") -ForegroundColor Green
