# Installs Windows Task Scheduler trigger every 1 minute.
# Pure ASCII for PS 5.1 W-1251 encoding compat (no Cyrillic to avoid quote-misparse).
# Run once via:  & 'D:\Projects\vps-monitor\client-monitor\install-task.ps1'

$TaskName = 'vps-monitor-client-probe'
$ScriptPath = 'D:\Projects\vps-monitor\client-monitor\probe.ps1'

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host 'Removing existing task...'
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptPath`""

$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 55) `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description 'Probes 4 plyeyada production URLs every 1 minute. Writes to client-probe-log.csv. For diagnostic triangulation.'

Write-Host ''
Write-Host '=== Task installed ==='
Write-Host "Task name: $TaskName"
Write-Host "Script: $ScriptPath"
Write-Host 'Frequency: every 1 minute'
Write-Host 'Log file: D:\Projects\vps-monitor\client-monitor\client-probe-log.csv'
Write-Host ''
Write-Host 'Verify task: Get-ScheduledTask -TaskName vps-monitor-client-probe'
Write-Host 'Run now:     Start-ScheduledTask -TaskName vps-monitor-client-probe'
Write-Host 'Stop later:  see README.md'
