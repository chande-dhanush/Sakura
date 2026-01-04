# Sakura V10 - Startup Manager (Windows)
$ErrorActionPreference = "Stop"

$ShortcutName = "SakuraV10.lnk"
$StartupPath = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupPath $ShortcutName
$TargetScript = (Get-Item ".\run_background.vbs").FullName
$IconPath = (Get-Item ".\backend\assets\icon.ico").FullName # Assuming icon exists, else default

Write-Host "🌸 Sakura V10 - Autostart Configuration" -ForegroundColor Magenta
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
        $wshShell = New-Object -ComObject WScript.Shell
        $shortcut = $wshShell.CreateShortcut($ShortcutPath)
        $shortcut.TargetPath = $TargetScript
        $shortcut.WorkingDirectory = (Get-Item ".").FullName
        $shortcut.Description = "Sakura V10 AI Assistant"
        # Optional: Set Icon if exists
        # $shortcut.IconLocation = "$IconPath,0"
        $shortcut.Save()
        Write-Host "🚀 Added to startup!" -ForegroundColor Green
    } else {
        Write-Host "👍 Kept disabled." -ForegroundColor Gray
    }
}

Write-Host "`nPress Enter to exit..."
Read-Host
