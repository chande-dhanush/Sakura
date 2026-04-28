<# 
.SYNOPSIS
    Rebuilds only the Sakura Backend binary and updates the Tauri sidecar.
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

Write-Host "Building Sakura Backend (Fast Path)..." -ForegroundColor Cyan

# Check Environment
$venvPath = Join-Path $ProjectRoot "PA"
if (-not (Test-Path "$venvPath\Scripts\activate.ps1")) {
    throw "Virtual Env 'PA' not found. Run scripts\setup.ps1 first."
}

# Build - Let backend.spec and hooks handle everything
Set-Location (Join-Path $ProjectRoot "backend")
& "$venvPath\Scripts\Activate.ps1"

$buildFlags = "--noconfirm"
if ($Clean) {
    $buildFlags += " --clean"
    Write-Host "  CLEAN build requested..." -ForegroundColor Yellow
}

# Use the venv's pyinstaller directly
& "$venvPath\Scripts\pyinstaller" backend.spec $buildFlags

Set-Location $ProjectRoot

# Move binary
$Source = Join-Path $ProjectRoot "backend\dist\sakura-backend.exe"

# Architecture Detection
$Arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "aarch64" } else { "x86_64" }
$Dest = Join-Path $ProjectRoot "frontend\src-tauri\binaries\sakura-backend-$Arch-pc-windows-msvc.exe"

if (Test-Path $Source) {
    $binDir = Split-Path -Parent $Dest
    if (-not (Test-Path $binDir)) {
        New-Item -ItemType Directory -Path $binDir | Out-Null
    }
    
    Copy-Item $Source $Dest -Force
    Write-Host "Success! Updated binary at: $Dest" -ForegroundColor Green
} else {
    Write-Error "Build failed. $Source not found."
}
