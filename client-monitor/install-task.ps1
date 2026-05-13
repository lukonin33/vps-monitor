# Установить Windows Task Scheduler trigger каждую 1 минуту.
# Запускается ОДИН РАЗ от Maxim, потом probe.ps1 крутится автоматически.
#
# Запускать: Right-click → Run with PowerShell (или через PowerShell admin).
# Если запрашивает privileges — accept.

$TaskName = 'vps-monitor-client-probe'
$ScriptPath = 'D:\Projects\vps-monitor\client-monitor\probe.ps1'

# Удалить старый task если был
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing task..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Action: запускать probe.ps1 через powershell.exe
$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`""

# Trigger: at startup + repeat every 1 minute, indefinitely
$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration ([TimeSpan]::MaxValue)).Repetition

# Settings: discard if running >55s, prevent overlaps
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 55) `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries

# Register без admin (user-level)
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description 'Probes 4 plyeyada production URLs каждую 1 минуту, пишет в client-probe-log.csv. Для диагностики client-side vs server-side outages.'

Write-Host ""
Write-Host "=== Task installed ==="
Write-Host "Task name: $TaskName"
Write-Host "Script: $ScriptPath"
Write-Host "Frequency: every 1 minute"
Write-Host "Log file: D:\Projects\vps-monitor\client-monitor\client-probe-log.csv"
Write-Host ""
Write-Host "First run will happen at next minute boundary."
Write-Host "Verify через:  Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "Run manually:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "To stop later: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
