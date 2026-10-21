# Registers the daily news archive run in the Windows Task Scheduler.
#
# Without -Register this script only prints what it would register. Register only after
# operator approval:   powershell -ExecutionPolicy Bypass -File scripts\news_archive_task.ps1 -Register
#
# The trigger time 06:30 is machine local time; this machine runs on Europe/Berlin.
# The task runs only while the user is logged on (no stored password). A missed or failed
# run needs no scheduler restart: the next daily run catches up (news_archive.py run --catch-up).
param([switch]$Register)

$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$python = "$repo\.venv\Scripts\python.exe"
$taskPath = "\TradingEngineX\"
$taskName = "NewsArchive"

$action = New-ScheduledTaskAction -Execute $python -Argument "scripts\news_archive.py run --catch-up" -WorkingDirectory $repo
# 06:30 local time (Europe/Berlin on this machine).
$trigger = New-ScheduledTaskTrigger -Daily -At 06:30
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Write-Host "Task:      $taskPath$taskName"
Write-Host "Execute:   $python"
Write-Host "Arguments: scripts\news_archive.py run --catch-up"
Write-Host "WorkDir:   $repo"
Write-Host "Trigger:   daily 06:30 (local time, Europe/Berlin)"
Write-Host "Settings:  StartWhenAvailable, MultipleInstances IgnoreNew, ExecutionTimeLimit 3h, no restart (next run catches up)"

if ($Register) {
    Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "TradingEngineX news archive (GDELT + AMF/DILA), daily with catch-up" | Out-Null
    Write-Host "Registered. Check with: Get-ScheduledTask -TaskPath '$taskPath' -TaskName '$taskName'"
    Write-Host "or: schtasks /query /tn `"$taskPath$taskName`" /xml"
} else {
    Write-Host "not registered; rerun with -Register after operator approval"
}
