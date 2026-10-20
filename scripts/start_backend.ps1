# 仅启动后端 API（自动选端口 8000-8099）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BackendDir = Join-Path $Root "backend"
$DevDir = Join-Path $Root ".dev"
$Python = Join-Path $BackendDir ".venv\Scripts\python.exe"
$FindPort = Join-Path $Root "scripts\find_free_port.py"
$CleanupPorts = Join-Path $Root "scripts\cleanup_stale_ports.py"
$PortsFile = Join-Path $DevDir "ports.json"

if (-not (Test-Path $Python)) {
    Write-Host "Run scripts/start_dev.ps1 first to create venv." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $DevDir | Out-Null

Write-Host "Cleaning stale backend ports..." -ForegroundColor Yellow
& $Python $CleanupPorts --start 8000 --end 8099 --ports-file $PortsFile
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] cleanup_stale_ports exited with code $LASTEXITCODE" -ForegroundColor DarkYellow
}

$Port = [int](& $Python $FindPort --start 8000 --end 8099)
@{ backend = $Port; started_at = (Get-Date).ToString("o") } | ConvertTo-Json | Set-Content (Join-Path $DevDir "ports.json") -Encoding UTF8

Write-Host "FBA Backend: http://127.0.0.1:$Port" -ForegroundColor Green
Push-Location $BackendDir
& $Python -m uvicorn main:app --host 127.0.0.1 --port $Port --reload
