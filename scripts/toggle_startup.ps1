# Sakura V13 - Startup Manager (Windows)
# Run from scripts/ folder

$ErrorActionPreference = "Stop"

# Get paths
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

$ShortcutName = "SakuraV13.lnk"
$StartupPath = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupPath $ShortcutName
$TargetScript = Join-Path $ScriptDir "run_background.vbs"

Write-Host "🌸 Sakura V13 - Autostart Configuration" -ForegroundColor Magenta
Write-Host "Startup Folder: $StartupPath" -ForegroundColor Gray

if (Test-Path $ShortcutPath) {
    Write-Host "`n✅ Status: ENABLED (Starts with Windows)" -ForegroundColor Green
    $choice = Read-Host "Do you want to DISABLE autostart? (y/n)"
    if ($choice -eq 'y') {
        Remove-Item $ShortcutPath -Force
        Write-Host "🗑️  Removed from startup." -ForegroundColor Yellow
    } else {
        Write-Host "👍 Kept enabled." -ForegroundColor Gray
    }
} else {
    Write-Host "`n❌ Status: DISABLED (Manual Run Only)" -ForegroundColor Yellow
    $choice = Read-Host "Do you want to ENABLE autostart? (y/n)"
    if ($choice -eq 'y') {
        # Check if VBS exists
        if (-not (Test-Path $TargetScript)) {
            Write-Host "❌ run_background.vbs not found at: $TargetScript" -ForegroundColor Red
            exit 1
        }
        
        $wshShell = New-Object -ComObject WScript.Shell
        $shortcut = $wshShell.CreateShortcut($ShortcutPath)
        $shortcut.TargetPath = $TargetScript
        $shortcut.WorkingDirectory = $ProjectRoot
        $shortcut.Description = "Sakura V13 AI Assistant"
        $shortcut.Save()
        Write-Host "🚀 Added to startup!" -ForegroundColor Green
    } else {
        Write-Host "👍 Kept disabled." -ForegroundColor Gray
    }
}

Write-Host "`nPress Enter to exit..."
Read-Host
