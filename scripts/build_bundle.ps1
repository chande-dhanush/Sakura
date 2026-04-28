<# 
.SYNOPSIS
    Sakura V18.3 - Full Bundle Builder
.DESCRIPTION
    Creates a complete distributable package with frontend and backend bundled together.
    Optimized for incremental builds.
.PARAMETER Clean
    If specified, clears PyInstaller caches and performs a fresh build.
#>

param (
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

# Get project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "Sakura V18.3 - Full Bundle Builder" -ForegroundColor Magenta
Write-Host "=================================" -ForegroundColor Magenta

# 0. Check Environment Dependencies
Write-Host "[Step 0] Checking prerequisites..." -ForegroundColor Cyan
if (!(Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: npm not found. Please install Node.js." -ForegroundColor Red
    exit 1
}
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: python not found. Please install Python." -ForegroundColor Red
    exit 1
}
Write-Host "  OK: Prerequisites met" -ForegroundColor Green

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

# Smart PyInstaller Check (Optimization C1)
$pyInstallerPath = Get-Command pyinstaller -ErrorAction SilentlyContinue
if (-not $pyInstallerPath) {
    Write-Host "  PyInstaller not found. Installing..." -ForegroundColor Gray
    pip install pyinstaller --quiet
} else {
    Write-Host "  PyInstaller already present, skipping install." -ForegroundColor Gray
}

# Run PyInstaller (Optimization C2: Smart Cache)
$buildFlags = "--noconfirm"
if ($Clean) {
    $buildFlags += " --clean"
    Write-Host "  CLEAN build requested. Clearing caches..." -ForegroundColor Yellow
}

Write-Host "  Running PyInstaller (Detailed log: backend/build.log)..." -ForegroundColor Gray
$PyInstallerLog = Join-Path (Get-Location) "build.log"

try {
    # Using cmd /c to bypass PowerShell's aggressive stderr stream interception
    cmd /c "pyinstaller backend.spec $buildFlags > ""$PyInstallerLog"" 2>&1"
} catch {
    Write-Host "ERROR: Build process crashed." -ForegroundColor Red
}

# Check if build succeeded
$BackendExe = Join-Path $ProjectRoot "backend\dist\sakura-backend.exe"
if (-not (Test-Path $BackendExe)) {
    Write-Host "ERROR: Backend build failed! Check backend\build.log" -ForegroundColor Red
    if (Test-Path "$PyInstallerLog") { Get-Content "$PyInstallerLog" -Tail 20 }
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

# Optimization C4: Architecture-Aware Sidecar
$Arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "aarch64" } else { "x86_64" }
$Target = "$Arch-pc-windows-msvc"
$DestPath = Join-Path $SidecarDir "sakura-backend-$Target.exe"

try {
    Copy-Item $BackendExe $DestPath -Force
    Write-Host "  OK: Copied to $DestPath" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Failed to copy sidecar. Is Sakura currently running?" -ForegroundColor Red
    exit 1
}

Set-Location $ProjectRoot

# 4. Build Tauri
Write-Host ""
Write-Host "[Step 4] Building Tauri frontend..." -ForegroundColor Cyan
Set-Location (Join-Path $ProjectRoot "frontend")

# Optimization C3: node_modules check
if (-not (Test-Path "node_modules")) {
    Write-Host "  node_modules missing. Running npm install..." -ForegroundColor Gray
    npm install
}

npm run tauri build

# Done
Set-Location $ProjectRoot
Write-Host ""
Write-Host "BUILD COMPLETE!" -ForegroundColor Green
Write-Host "===============" -ForegroundColor Green
Write-Host "Installer: frontend\src-tauri\target\release\bundle\nsis\Sakura_18.0.0_x64-setup.exe" -ForegroundColor White
