# FBA Smart Tool — 开发环境一键启动（自动避让端口冲突）
# Usage: powershell -ExecutionPolicy Bypass -File scripts/start_dev.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$DevDir = Join-Path $Root ".dev"
$PortsFile = Join-Path $DevDir "ports.json"
$Python = Join-Path $BackendDir ".venv\Scripts\python.exe"
$FindPort = Join-Path $Root "scripts\find_free_port.py"
$CleanupPorts = Join-Path $Root "scripts\cleanup_stale_ports.py"

function Find-Port([int]$Start, [int]$End) {
    & $Python $FindPort --start $Start --end $End
    if ($LASTEXITCODE -ne 0) { throw "find_free_port failed ($Start-$End)" }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " FBA Smart Tool - Dev (auto port)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $Python)) {
    Write-Host "[1/6] Creating backend venv..." -ForegroundColor Yellow
    Push-Location $BackendDir
    py -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Python not found. Install Python 3.10+ first." -ForegroundColor Red
        exit 1
    }
    Pop-Location
}

Write-Host "[2/6] Checking backend dependencies..." -ForegroundColor Yellow
Push-Location $BackendDir
& $Python -m pip install -q -r requirements.txt
Pop-Location

Write-Host "[3/6] Cleaning stale backend ports..." -ForegroundColor Yellow
& $Python $CleanupPorts --start 8000 --end 8099 --ports-file $PortsFile
if ($LASTEXITCODE -ne 0) {
    Write-Host "      [WARN] cleanup_stale_ports exited with code $LASTEXITCODE" -ForegroundColor DarkYellow
}

Write-Host "[4/6] Resolving free ports..." -ForegroundColor Yellow
$BackendPort = [int](Find-Port -Start 8000 -End 8099)
$FrontendPort = [int](Find-Port -Start 5173 -End 5199)

New-Item -ItemType Directory -Force -Path $DevDir | Out-Null
@{
    backend    = $BackendPort
    frontend   = $FrontendPort
    started_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content -Path $PortsFile -Encoding UTF8

Write-Host "      Backend  -> http://127.0.0.1:$BackendPort" -ForegroundColor Green
Write-Host "      Frontend -> http://127.0.0.1:$FrontendPort" -ForegroundColor Green
Write-Host "      Ports file: .dev/ports.json" -ForegroundColor DarkGray

Write-Host "[5/6] Starting backend (new window)..." -ForegroundColor Yellow
$backendCmd = @"
Set-Location '$BackendDir'
`$host.UI.RawUI.WindowTitle = 'FBA Backend :$BackendPort'
Write-Host 'FBA API: http://127.0.0.1:$BackendPort' -ForegroundColor Green
Write-Host 'Docs:    http://127.0.0.1:$BackendPort/docs' -ForegroundColor DarkGray
Write-Host ''
& '$Python' -m uvicorn main:app --host 127.0.0.1 --port $BackendPort --reload
"@
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd | Out-Null

Start-Sleep -Seconds 2

Write-Host "[6/6] Starting frontend..." -ForegroundColor Yellow
# Re-pick frontend port immediately before bind (avoid race after backend window opens)
$FrontendPort = [int](Find-Port -Start 5173 -End 5199)
@{
    backend    = $BackendPort
    frontend   = $FrontendPort
    started_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content -Path $PortsFile -Encoding UTF8
Write-Host "      Frontend -> http://127.0.0.1:$FrontendPort" -ForegroundColor Green
Write-Host ""
Push-Location $FrontendDir

if (-not (Test-Path "node_modules")) {
    Write-Host "      Installing npm packages (first run)..." -ForegroundColor DarkGray
    npm install
}

$env:FBA_BACKEND_PORT = "$BackendPort"
npm run dev -- --port $FrontendPort --strictPort

Pop-Location
