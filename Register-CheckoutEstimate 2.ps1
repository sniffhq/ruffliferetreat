# Register-CheckoutEstimate.ps1
# Run as Administrator
# Sends estimated balance SMS to owners whose pets are checking out today
# Runs daily at 7:00 AM

$taskName   = "RuffLife-CheckoutEstimate"
$scriptPath = "C:\RuffLifeRetreat\app\checkout_estimate.py"
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

$trigger = New-ScheduledTaskTrigger -Daily -At "7:00AM"

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

Write-Host "Registered: $taskName - runs daily at 7:00 AM"
Write-Host "Log file: $logDir\checkout_estimate.log"