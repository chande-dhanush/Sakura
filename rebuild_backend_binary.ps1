$ErrorActionPreference = "Stop"

Write-Host "🚀 Building Sakura Backend..." -ForegroundColor Cyan

# Check Environment
if (-not (Test-Path "PA\Scripts\activate.ps1")) {
    throw "Virtual Env 'PA' not found. Run ./setup.ps1 first."
}

# Build
cd backend
..\PA\Scripts\pyinstaller backend.spec --clean --noconfirm
cd ..

# Move
$Source = "backend\dist\sakura-backend.exe"
$Dest = "frontend\src-tauri\binaries\sakura-backend-x86_64-pc-windows-msvc.exe"

if (Test-Path $Source) {
    if (-not (Test-Path "frontend\src-tauri\binaries")) {
        New-Item -ItemType Directory -Path "frontend\src-tauri\binaries" | Out-Null
    }
    
    Copy-Item $Source $Dest -Force
    Write-Host "✅ Success! Updated binary at: $Dest" -ForegroundColor Green
} else {
    Write-Error "❌ Build failed. $Source not found."
}
