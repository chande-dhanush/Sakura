$ErrorActionPreference = "Stop"

# Get project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

Write-Host "🚀 Building Sakura Backend..." -ForegroundColor Cyan

# Check Environment
$venvPath = Join-Path $ProjectRoot "PA"
if (-not (Test-Path "$venvPath\Scripts\activate.ps1")) {
    throw "Virtual Env 'PA' not found. Run scripts\setup.ps1 first."
}

# Build
Set-Location (Join-Path $ProjectRoot "backend")
& "$venvPath\Scripts\pyinstaller" backend.spec --clean --noconfirm
Set-Location $ProjectRoot

# Move
$Source = Join-Path $ProjectRoot "backend\dist\sakura-backend.exe"
$Dest = Join-Path $ProjectRoot "frontend\src-tauri\binaries\sakura-backend-x86_64-pc-windows-msvc.exe"

if (Test-Path $Source) {
    $binDir = Split-Path -Parent $Dest
    if (-not (Test-Path $binDir)) {
        New-Item -ItemType Directory -Path $binDir | Out-Null
    }
    
    Copy-Item $Source $Dest -Force
    Write-Host "✅ Success! Updated binary at: $Dest" -ForegroundColor Green
} else {
    Write-Error "❌ Build failed. $Source not found."
}
