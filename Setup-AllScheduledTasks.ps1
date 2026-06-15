# Setup-AllScheduledTasks.ps1
# Run this once as Administrator to register ALL Ruff Life Retreat scheduled tasks.
# Safe to re-run — removes existing tasks before re-creating them.

$PythonExe = "C:\RuffLifeRetreat\venv\Scripts\python.exe"
$LogDir    = "C:\RuffLifeRetreat\logs"

# Create logs directory
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
    Write-Host "Created logs directory: $LogDir" -ForegroundColor Cyan
}

$tasks = @(
    @{
        Name        = "RuffLife - Daily Vaccination Alerts"
        Script      = "C:\RuffLifeRetreat\app\vaccination_alerts.py"
        Trigger     = New-ScheduledTaskTrigger -Daily -At "08:00AM"
        Description = "Checks vaccination records expiring in 7 or 30 days and sends SMS alerts to staff and pet owners."
    },
    @{
        Name        = "RuffLife - Daily Appointment Reminders"
        Script      = "C:\RuffLifeRetreat\app\appointment_reminders.py"
        Trigger     = New-ScheduledTaskTrigger -Daily -At "08:00AM"
        Description = "Sends 24-hour appointment reminder SMS to customers with appointments tomorrow."
    },
    @{
        Name        = "RuffLife - Weekly Survey Batch"
        Script      = "C:\RuffLifeRetreat\app\survey_batch.py"
        Trigger     = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "10:00AM"
        Description = "Sends satisfaction surveys to customers not surveyed in the past 90 days."
    }
)

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RestartCount 1 `
    -RestartInterval (New-TimeSpan -Minutes 2) `
    -StartWhenAvailable

$Principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

foreach ($task in $tasks) {
    # Remove existing task if present
    if (Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $task.Name -Confirm:$false
        Write-Host "Removed existing task: $($task.Name)" -ForegroundColor Yellow
    }

    $Action = New-ScheduledTaskAction `
        -Execute $PythonExe `
        -Argument $task.Script `
        -WorkingDirectory "C:\RuffLifeRetreat"

    Register-ScheduledTask `
        -TaskName   $task.Name `
        -Action     $Action `
        -Trigger    $task.Trigger `
        -Settings   $Settings `
        -Principal  $Principal `
        -Description $task.Description | Out-Null

    Write-Host "✓ Registered: $($task.Name)" -ForegroundColor Green
}

Write-Host ""
Write-Host "All scheduled tasks registered!" -ForegroundColor Green
Write-Host ""
Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "  Daily  08:00 AM  — Vaccination Alerts"
Write-Host "  Daily  08:00 AM  — Appointment Reminders"
Write-Host "  Weekly Sunday 10:00 AM — Survey Batch"
Write-Host ""
Write-Host "Log files will be written to: $LogDir"
Write-Host ""
Write-Host "To test immediately, run:"
Write-Host "  Start-ScheduledTask -TaskName 'RuffLife - Weekly Survey Batch'" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName 'RuffLife - Daily Vaccination Alerts'" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName 'RuffLife - Daily Appointment Reminders'" -ForegroundColor Yellow