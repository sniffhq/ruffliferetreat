# Ruff Life Retreat - Database Restore Script
# Use this to restore from a backup
#
# Usage: .\restore_database.ps1
# Or:    .\restore_database.ps1 -BackupFile "C:\RuffLifeRetreat\backups\ruff_life_2025-11-27_020000.db.zip"

param(
    [string]$AppPath = "C:\RuffLifeRetreat",
    [string]$BackupPath = "C:\RuffLifeRetreat\backups",
    [string]$BackupFile = ""
)

$DatabaseName = "ruff_life.db"
$DatabasePath = Join-Path $AppPath "instance\$DatabaseName"

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "RUFF LIFE RETREAT - DATABASE RESTORE" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""

# If no backup file specified, show available backups
if (-not $BackupFile) {
    Write-Host "Available backups:" -ForegroundColor Yellow
    Write-Host ""
    
    $backups = Get-ChildItem -Path $BackupPath -Filter "ruff_life_*.db*" | 
               Sort-Object LastWriteTime -Descending
    
    if ($backups.Count -eq 0) {
        Write-Host "No backups found in $BackupPath" -ForegroundColor Red
        exit 1
    }
    
    for ($i = 0; $i -lt $backups.Count; $i++) {
        $backup = $backups[$i]
        $size = [math]::Round($backup.Length / 1MB, 2)
        $date = $backup.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
        Write-Host "  [$($i + 1)] $($backup.Name) - $size MB - $date"
    }
    
    Write-Host ""
    $selection = Read-Host "Enter backup number to restore (or 'q' to quit)"
    
    if ($selection -eq 'q') {
        Write-Host "Restore cancelled." -ForegroundColor Yellow
        exit 0
    }
    
    try {
        $index = [int]$selection - 1
        if ($index -lt 0 -or $index -ge $backups.Count) {
            throw "Invalid selection"
        }
        $BackupFile = $backups[$index].FullName
    }
    catch {
        Write-Host "Invalid selection. Restore cancelled." -ForegroundColor Red
        exit 1
    }
}

# Verify backup file exists
if (-not (Test-Path $BackupFile)) {
    Write-Host "ERROR: Backup file not found: $BackupFile" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Selected backup: $BackupFile" -ForegroundColor Green
Write-Host "Target database: $DatabasePath" -ForegroundColor Green
Write-Host ""
Write-Host "WARNING: This will REPLACE the current database!" -ForegroundColor Red
Write-Host "The current database will be backed up first." -ForegroundColor Yellow
Write-Host ""

$confirm = Read-Host "Type 'RESTORE' to confirm"
if ($confirm -ne 'RESTORE') {
    Write-Host "Restore cancelled." -ForegroundColor Yellow
    exit 0
}

try {
    # Backup current database first
    $preRestoreBackup = Join-Path $BackupPath "pre_restore_$(Get-Date -Format 'yyyy-MM-dd_HHmmss').db"
    if (Test-Path $DatabasePath) {
        Copy-Item -Path $DatabasePath -Destination $preRestoreBackup -Force
        Write-Host "Current database backed up to: $preRestoreBackup" -ForegroundColor Green
    }
    
    # Check if backup is compressed
    if ($BackupFile -match '\.zip$') {
        Write-Host "Extracting compressed backup..." -ForegroundColor Cyan
        $tempDir = Join-Path $env:TEMP "ruff_restore_$(Get-Date -Format 'yyyyMMddHHmmss')"
        Expand-Archive -Path $BackupFile -DestinationPath $tempDir -Force
        $extractedDb = Get-ChildItem -Path $tempDir -Filter "*.db" | Select-Object -First 1
        
        if (-not $extractedDb) {
            throw "No .db file found in backup archive"
        }
        
        Copy-Item -Path $extractedDb.FullName -Destination $DatabasePath -Force
        Remove-Item -Path $tempDir -Recurse -Force
    }
    else {
        Copy-Item -Path $BackupFile -Destination $DatabasePath -Force
    }
    
    Write-Host ""
    Write-Host "=" * 60 -ForegroundColor Green
    Write-Host "DATABASE RESTORED SUCCESSFULLY!" -ForegroundColor Green
    Write-Host "=" * 60 -ForegroundColor Green
    Write-Host ""
    Write-Host "Please restart the Ruff Life Retreat application." -ForegroundColor Yellow
}
catch {
    Write-Host "ERROR: Restore failed - $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "If the database is corrupted, you can restore the pre-restore backup:" -ForegroundColor Yellow
    Write-Host "  Copy-Item '$preRestoreBackup' '$DatabasePath' -Force" -ForegroundColor White
    exit 1
}