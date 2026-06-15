# Register-NoVaccineFollowup.ps1
# Run as Administrator to register the daily no-vaccine followup task
# Runs every day at 10:30 AM (30 minutes after the no-pet followup)

$taskName   = "RuffLife-NoVaccineFollowup"
$scriptPath = "C:\RuffLifeRetreat\app\no_vaccine_followup.py"
$python     = "C:\RuffLifeRetreat\venv\Scripts\python.exe"
$logDir     = "C:\RuffLifeRetreat\logs"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
    Write-Host "Created logs directory: $logDir"
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Removed existing task: $taskName"
}

$action  = New-ScheduledTaskAction `
    -Execute $python `
    -Argument $scriptPath `
    -WorkingDirectory "C:\RuffLifeRetreat"

$trigger = New-ScheduledTaskTrigger -Daily -At "10:30AM"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "Registered: $taskName — runs daily at 10:30 AM"
Write-Host "Log file: $logDir\no_vaccine_followup.log"