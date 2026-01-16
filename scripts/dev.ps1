# Sakura Development Launcher
# ============================
# Runs backend server directly (no PyInstaller build) + frontend dev server
# Usage: .\scripts\dev.ps1

$ErrorActionPreference = "Stop"

Write-Host "🌸 Starting Sakura Development Environment..." -ForegroundColor Magenta

# Get project root
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"

# Check if virtual environment exists
$VenvPath = Join-Path $ProjectRoot "PA\Scripts\Activate.ps1"
if (-not (Test-Path $VenvPath)) {
    Write-Host "❌ Virtual environment not found at PA\Scripts\Activate.ps1" -ForegroundColor Red
    Write-Host "Run .\scripts\setup.ps1 first." -ForegroundColor Yellow
    exit 1
}

# Start Backend in background
Write-Host "`n🐍 Starting Backend Server (port 3210)..." -ForegroundColor Cyan
$backendJob = Start-Job -Name "SakuraBackend" -ScriptBlock {
    param($ProjectRoot, $BackendDir)
    Set-Location $BackendDir
    & "$ProjectRoot\PA\Scripts\Activate.ps1"
    $env:SAKURA_PORT = "3210"
    python server.py
} -ArgumentList $ProjectRoot, $BackendDir

Write-Host "   Backend running in background (Job ID: $($backendJob.Id))" -ForegroundColor Gray

# Wait for backend to be ready
Write-Host "`n⏳ Waiting for backend to start..." -ForegroundColor Yellow
$maxWait = 30
$waited = 0
while ($waited -lt $maxWait) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:3210/health" -Method GET -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            Write-Host "✅ Backend ready!" -ForegroundColor Green
            break
        }
    } catch {
        # Backend not ready yet
    }
    Start-Sleep -Seconds 1
    $waited++
    Write-Host "." -NoNewline
}

if ($waited -ge $maxWait) {
    Write-Host "`n⚠️ Backend took too long to start. Check logs." -ForegroundColor Yellow
}

# Start Frontend
Write-Host "`n🎨 Starting Frontend (Tauri Dev)..." -ForegroundColor Cyan
Set-Location $FrontendDir

# Run Tauri dev (this will block)
npm run tauri dev

# Cleanup when frontend exits
Write-Host "`n🧹 Cleaning up..." -ForegroundColor Yellow
Stop-Job -Name "SakuraBackend" -ErrorAction SilentlyContinue
Remove-Job -Name "SakuraBackend" -ErrorAction SilentlyContinue

# Send shutdown signal to backend
try {
    Invoke-WebRequest -Uri "http://localhost:3210/shutdown" -Method POST -TimeoutSec 2 -ErrorAction SilentlyContinue | Out-Null
} catch {}

Write-Host "👋 Sakura stopped." -ForegroundColor Magenta
