<# 
.SYNOPSIS
    Sakura V10 - Full Bundle Builder
.DESCRIPTION
    Creates a complete distributable package with frontend and backend bundled together.
#>

$ErrorActionPreference = "Stop"

Write-Host "Sakura V10 - Full Bundle Builder" -ForegroundColor Magenta
Write-Host "=================================" -ForegroundColor Magenta

# Save starting directory
$RootDir = Get-Location

# 1. Check venv exists
Write-Host ""
Write-Host "[Step 1] Checking virtual environment..." -ForegroundColor Cyan
if (-not (Test-Path "PA\Scripts\Activate.ps1")) {
    Write-Host "ERROR: Virtual environment not found. Run setup.ps1 first!" -ForegroundColor Red
    exit 1
}
Write-Host "  OK: Virtual environment found" -ForegroundColor Green

# 2. Activate venv and build backend
Write-Host ""
Write-Host "[Step 2] Building backend executable..." -ForegroundColor Cyan

# Change to backend directory
Set-Location "backend"

# Activate venv (run in same session)
& "$RootDir\PA\Scripts\Activate.ps1"

# Install PyInstaller if needed
Write-Host "  Installing PyInstaller..." -ForegroundColor Gray
pip install pyinstaller --quiet

# Run PyInstaller
Write-Host "  Running PyInstaller..." -ForegroundColor Gray
pyinstaller backend.spec --clean --noconfirm 2>&1 | Out-Null

# Check if build succeeded
$BackendExe = Join-Path (Get-Location) "dist\sakura-backend.exe"
if (-not (Test-Path $BackendExe)) {
    Write-Host "ERROR: Backend build failed! Check backend.spec" -ForegroundColor Red
    Set-Location $RootDir
    exit 1
}
Write-Host "  OK: Backend built at $BackendExe" -ForegroundColor Green

# 3. Copy to Tauri sidecar location
Write-Host ""
Write-Host "[Step 3] Copying to Tauri sidecar..." -ForegroundColor Cyan

$SidecarDir = Join-Path $RootDir "frontend\src-tauri\binaries"
if (-not (Test-Path $SidecarDir)) {
    New-Item -ItemType Directory -Path $SidecarDir -Force | Out-Null
}

# Tauri expects: {name}-{target}.exe
$Target = "x86_64-pc-windows-msvc"
$DestPath = Join-Path $SidecarDir "sakura-backend-$Target.exe"
Copy-Item $BackendExe $DestPath -Force
Write-Host "  OK: Copied to $DestPath" -ForegroundColor Green

# Return to root
Set-Location $RootDir

# 4. Build Tauri
Write-Host ""
Write-Host "[Step 4] Building Tauri frontend..." -ForegroundColor Cyan
Set-Location "frontend"
npm run tauri build

# Done
Set-Location $RootDir
Write-Host ""
Write-Host "BUILD COMPLETE!" -ForegroundColor Green
Write-Host "===============" -ForegroundColor Green
Write-Host "Installer: frontend\src-tauri\target\release\bundle\nsis\Sakura_10.0.0_x64-setup.exe" -ForegroundColor White
