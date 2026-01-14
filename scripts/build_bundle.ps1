<# 
.SYNOPSIS
    Sakura V13 - Full Bundle Builder
.DESCRIPTION
    Creates a complete distributable package with frontend and backend bundled together.
    Run from scripts/ folder.
#>

$ErrorActionPreference = "Stop"

# Get project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "Sakura V13 - Full Bundle Builder" -ForegroundColor Magenta
Write-Host "=================================" -ForegroundColor Magenta

# 1. Check venv exists
Write-Host ""
Write-Host "[Step 1] Checking virtual environment..." -ForegroundColor Cyan
$venvPath = Join-Path $ProjectRoot "PA"
if (-not (Test-Path "$venvPath\Scripts\Activate.ps1")) {
    Write-Host "ERROR: Virtual environment not found. Run scripts\setup.ps1 first!" -ForegroundColor Red
    exit 1
}
Write-Host "  OK: Virtual environment found" -ForegroundColor Green

# 2. Activate venv and build backend
Write-Host ""
Write-Host "[Step 2] Building backend executable..." -ForegroundColor Cyan

Set-Location (Join-Path $ProjectRoot "backend")

# Activate venv
& "$venvPath\Scripts\Activate.ps1"

# Install PyInstaller if needed
Write-Host "  Installing PyInstaller..." -ForegroundColor Gray
pip install pyinstaller --quiet

# Run PyInstaller
Write-Host "  Running PyInstaller..." -ForegroundColor Gray
pyinstaller backend.spec --clean --noconfirm 2>&1 | Out-Null

# Check if build succeeded
$BackendExe = Join-Path $ProjectRoot "backend\dist\sakura-backend.exe"
if (-not (Test-Path $BackendExe)) {
    Write-Host "ERROR: Backend build failed! Check backend.spec" -ForegroundColor Red
    Set-Location $ProjectRoot
    exit 1
}
Write-Host "  OK: Backend built at $BackendExe" -ForegroundColor Green

# 3. Copy to Tauri sidecar location
Write-Host ""
Write-Host "[Step 3] Copying to Tauri sidecar..." -ForegroundColor Cyan

$SidecarDir = Join-Path $ProjectRoot "frontend\src-tauri\binaries"
if (-not (Test-Path $SidecarDir)) {
    New-Item -ItemType Directory -Path $SidecarDir -Force | Out-Null
}

$Target = "x86_64-pc-windows-msvc"
$DestPath = Join-Path $SidecarDir "sakura-backend-$Target.exe"
Copy-Item $BackendExe $DestPath -Force
Write-Host "  OK: Copied to $DestPath" -ForegroundColor Green

Set-Location $ProjectRoot

# 4. Build Tauri
Write-Host ""
Write-Host "[Step 4] Building Tauri frontend..." -ForegroundColor Cyan
Set-Location (Join-Path $ProjectRoot "frontend")
npm run tauri build

# Done
Set-Location $ProjectRoot
Write-Host ""
Write-Host "BUILD COMPLETE!" -ForegroundColor Green
Write-Host "===============" -ForegroundColor Green
Write-Host "Installer: frontend\src-tauri\target\release\bundle\nsis\Sakura_13.0.0_x64-setup.exe" -ForegroundColor White
