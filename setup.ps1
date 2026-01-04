# Sakura V10 - Windows Setup Script
# Run as Administrator: .\setup.ps1

$ErrorActionPreference = "Stop"
Write-Host "🌸 Sakura V10 Setup Script" -ForegroundColor Magenta
Write-Host "=========================" -ForegroundColor Magenta

# Check Admin
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "⚠️  Please run this script as Administrator!" -ForegroundColor Yellow
    exit 1
}

# --- 1. Check Python ---
Write-Host "`n📦 Checking Python..." -ForegroundColor Cyan
try {
    $pythonVersion = python --version 2>&1
    Write-Host "   ✅ $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "   ❌ Python not found. Installing via winget..." -ForegroundColor Red
    winget install Python.Python.3.11 --silent
}

# --- 2. Check Node.js ---
Write-Host "`n📦 Checking Node.js..." -ForegroundColor Cyan
try {
    $nodeVersion = node --version 2>&1
    Write-Host "   ✅ Node.js $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "   ❌ Node.js not found. Installing via winget..." -ForegroundColor Red
    winget install OpenJS.NodeJS.LTS --silent
}

# --- 3. Check Rust ---
Write-Host "`n📦 Checking Rust (for Tauri)..." -ForegroundColor Cyan
try {
    $rustVersion = rustc --version 2>&1
    Write-Host "   ✅ $rustVersion" -ForegroundColor Green
} catch {
    Write-Host "   ❌ Rust not found. Installing via winget..." -ForegroundColor Red
    winget install Rustlang.Rustup --silent
    Write-Host "   ⚠️  Please restart your terminal after Rust installation!" -ForegroundColor Yellow
}

# --- 4. Optional: Tesseract OCR (for screen reading) ---
Write-Host "`n📦 [Optional] Checking Tesseract OCR..." -ForegroundColor Cyan
$tesseractPath = "C:\Program Files\Tesseract-OCR\tesseract.exe"
if (Test-Path $tesseractPath) {
    Write-Host "   ✅ Tesseract installed" -ForegroundColor Green
} else {
    Write-Host "   ⚠️  Tesseract not found (screen reading disabled)" -ForegroundColor Yellow
    Write-Host "   To install: winget install UB-Mannheim.TesseractOCR" -ForegroundColor Gray
}

# --- 5. Create Virtual Environment ---
Write-Host "`n🐍 Setting up Python virtual environment..." -ForegroundColor Cyan
$venvPath = ".\PA"
if (-not (Test-Path $venvPath)) {
    python -m venv $venvPath
    Write-Host "   ✅ Created venv at $venvPath" -ForegroundColor Green
} else {
    Write-Host "   ✅ Venv already exists" -ForegroundColor Green
}

# --- 6. Install Python Dependencies ---
Write-Host "`n📥 Installing Python dependencies..." -ForegroundColor Cyan
& "$venvPath\Scripts\pip.exe" install -r backend\requirements.txt

# --- 7. Install Frontend Dependencies ---
Write-Host "`n📥 Installing Frontend dependencies..." -ForegroundColor Cyan
Set-Location frontend
npm install
Set-Location ..

# --- 8. Create .env file if missing ---
Write-Host "`n🔐 Checking .env file..." -ForegroundColor Cyan
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "   ⚠️  Created .env from template. Please add your API keys!" -ForegroundColor Yellow
    Write-Host "   Edit: .env" -ForegroundColor Gray
} else {
    Write-Host "   ✅ .env exists" -ForegroundColor Green
}

# --- Done ---
Write-Host "`n🎉 Setup Complete!" -ForegroundColor Green
Write-Host "==================" -ForegroundColor Green
Write-Host "To run Sakura:" -ForegroundColor Cyan
Write-Host "  cd frontend" -ForegroundColor White
Write-Host "  npm run tauri dev" -ForegroundColor White
Write-Host "`nTo build for production:" -ForegroundColor Cyan
Write-Host "  npm run tauri build" -ForegroundColor White

# --- 9. Startup Prompt ---
Write-Host "`n⚙️  Configuration" -ForegroundColor Cyan
if (Test-Path ".\toggle_startup.ps1") {
    powershell -ExecutionPolicy Bypass -File ".\toggle_startup.ps1"
}

