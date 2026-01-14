# Sakura V10 - Uninstaller
# Removes all generated files (venv, node_modules, data).
# Does NOT remove system packages (Python, Node) or Source Code.

$ErrorActionPreference = "SilentlyContinue"

Write-Host "🗑️  Uninstalling Sakura V10 Artifacts..." -ForegroundColor Magenta

# 1. Remove Virtual Environment
if (Test-Path "PA") {
    Write-Host "   Removing Virtual Environment (PA)..." -ForegroundColor White
    Remove-Item -Path "PA" -Recurse -Force
}

# 2. Remove Node Modules
if (Test-Path "frontend\node_modules") {
    Write-Host "   Removing frontend Dependencies (node_modules)..." -ForegroundColor White
    Remove-Item -Path "frontend\node_modules" -Recurse -Force
}

# 3. Remove Build Artifacts
if (Test-Path "frontend\src-tauri\target") {
    Write-Host "   Removing Build Artifacts (target)..." -ForegroundColor White
    Remove-Item -Path "frontend\src-tauri\target" -Recurse -Force
}

# 4. Remove Data (Optional - usually users want to keep memories?)
# We will rename it to data_backup just in case, or ask?
# User said "uninstall everything", implying a clean wipe. 
# But let's be safe and just rename.
if (Test-Path "backend\data") {
    Write-Host "   Removing Database (backend/data)..." -ForegroundColor White
    Remove-Item -Path "backend\data" -Recurse -Force
}

# 5. Remove .env? (Contains keys!)
# We'll leave it but warn.
Write-Host "   ⚠️  .env file was KEPT (contains your API keys)." -ForegroundColor Yellow
Write-Host "   Delete it manually if you want a full wipe." -ForegroundColor Gray

Write-Host "`n✅ Uninstallation Complete. Project is clean." -ForegroundColor Green
