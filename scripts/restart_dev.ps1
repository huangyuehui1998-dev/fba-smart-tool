# Stop this project's recorded frontend/backend (ports.json only), then start_dev.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"
$StopPy = Join-Path $Root "scripts\stop_dev.py"
$PortsFile = Join-Path $Root ".dev\ports.json"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " FBA Smart Tool - Restart" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path $Python) {
    Write-Host "[1/2] Stopping recorded frontend/backend..." -ForegroundColor Yellow
    & $Python $StopPy --ports-file $PortsFile
} else {
    Write-Host "[1/2] venv missing, skip stop" -ForegroundColor DarkYellow
}

Start-Sleep -Seconds 1
Write-Host "[2/2] Starting..." -ForegroundColor Yellow
& (Join-Path $Root "scripts\start_dev.ps1")
