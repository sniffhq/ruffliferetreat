# Setup-VaccinationAlerts.ps1
# Run this once as Administrator to register the daily vaccination alert task.
# After running, the check will fire every day at 8:00 AM automatically.

$TaskName   = "RuffLife - Daily Vaccination Alerts"
$PythonExe  = "C:\RuffLifeRetreat\venv\Scripts\python.exe"
$ScriptPath = "C:\RuffLifeRetreat\app\vaccination_alerts.py"
$LogDir     = "C:\RuffLifeRetreat\logs"

# Create logs directory if it doesn't exist
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
    Write-Host "Created logs directory: $LogDir"
}

# Remove existing task if present
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed existing task."
}

# Build the task
$Action  = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument $ScriptPath `
    -WorkingDirectory "C:\RuffLifeRetreat"

$Trigger = New-ScheduledTaskTrigger -Daily -At "08:00AM"

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable

$Principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Checks for vaccinations expiring in 7 or 30 days and sends SMS alerts to staff and customers." | Out-Null

Write-Host ""
Write-Host "✓ Scheduled task registered successfully!" -ForegroundColor Green
Write-Host "  Name    : $TaskName"
Write-Host "  Runs at : 8:00 AM daily"
Write-Host "  Script  : $ScriptPath"
Write-Host "  Logs    : $LogDir\vaccination_alerts.log"
Write-Host ""
Write-Host "To test immediately, run:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Yellow