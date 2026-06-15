# Ruff Life Retreat - Database Backup Script
# Schedule this with Windows Task Scheduler for automatic backups
#
# Usage: .\backup_database.ps1
# Optional: .\backup_database.ps1 -BackupPath "D:\Backups" -RetentionDays 30

param(
    [string]$AppPath = "C:\RuffLifeRetreat",
    [string]$BackupPath = "C:\RuffLifeRetreat\backups",
    [int]$RetentionDays = 14,
    [switch]$Compress = $true
)

# Configuration
$DatabaseName = "rufflife.db"
$DatabasePath = Join-Path $AppPath "instance\$DatabaseName"
$PythonExe    = Join-Path $AppPath "venv\Scripts\python.exe"
$LogFile      = Join-Path $BackupPath "backup_log.txt"
$Timestamp    = Get-Date -Format "yyyy-MM-dd_HHmmss"

function Write-Log {
    param([string]$Message)
    $LogEntry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $Message"
    Write-Host $LogEntry
    Add-Content -Path $LogFile -Value $LogEntry -ErrorAction SilentlyContinue
}

# Create backup directory if it doesn't exist
if (-not (Test-Path $BackupPath)) {
    New-Item -ItemType Directory -Path $BackupPath -Force | Out-Null
    Write-Log "Created backup directory: $BackupPath"
}

# Verify database exists
if (-not (Test-Path $DatabasePath)) {
    Write-Log "ERROR: Database not found at $DatabasePath"
    exit 1
}

# Verify Python venv exists
if (-not (Test-Path $PythonExe)) {
    Write-Log "ERROR: Python venv not found at $PythonExe"
    exit 1
}

# Get database file size
$DbSize = (Get-Item $DatabasePath).Length / 1MB
Write-Log "Starting backup of $DatabaseName ($([math]::Round($DbSize, 2)) MB)"

# Create backup filename
$BackupFileName = "ruff_life_$Timestamp.db"
$BackupFilePath = Join-Path $BackupPath $BackupFileName

try {
    # Use SQLite's built-in online backup API via Python.
    # This is WAL-safe — it checkpoints properly and produces a clean copy
    # even while Flask is actively reading/writing the database.
    $PythonBackupScript = @"
import sqlite3, sys, os
src_path = sys.argv[1]
dst_path = sys.argv[2]
try:
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    src.backup(dst)
    dst.close()
    src.close()
    size = os.path.getsize(dst_path)
    if size == 0:
        print('ERROR: Backup produced a zero-byte file')
        sys.exit(1)
    print(f'OK:{size}')
except Exception as e:
    print(f'ERROR:{e}')
    sys.exit(1)
"@

    $result = & $PythonExe -c $PythonBackupScript $DatabasePath $BackupFilePath 2>&1

    if ($LASTEXITCODE -ne 0 -or $result -like "ERROR*") {
        Write-Log "ERROR: SQLite backup failed - $result"
        exit 1
    }

    # Parse the returned file size from Python for accurate logging
    $BackupSizeBytes = ($result -replace "OK:", "") -as [long]
    $BackupSizeMB    = [math]::Round($BackupSizeBytes / 1MB, 2)
    Write-Log "Database backed up to: $BackupFilePath ($BackupSizeMB MB)"

    # Compress if enabled
    if ($Compress) {
        $ZipPath = "$BackupFilePath.zip"
        Compress-Archive -Path $BackupFilePath -DestinationPath $ZipPath -Force
        Remove-Item $BackupFilePath -Force
        $ZipSize = [math]::Round((Get-Item $ZipPath).Length / 1MB, 2)
        Write-Log "Compressed to: $ZipPath ($ZipSize MB)"
        $BackupFilePath = $ZipPath
    }

    Write-Log "Backup completed successfully!"
}
catch {
    Write-Log "ERROR: Backup failed - $_"
    exit 1
}

# Cleanup old backups
Write-Log "Checking for backups older than $RetentionDays days..."
$CutoffDate = (Get-Date).AddDays(-$RetentionDays)
$OldBackups = Get-ChildItem -Path $BackupPath -Filter "ruff_life_*.db*" |
              Where-Object { $_.LastWriteTime -lt $CutoffDate }

if ($OldBackups.Count -gt 0) {
    foreach ($OldBackup in $OldBackups) {
        Remove-Item $OldBackup.FullName -Force
        Write-Log "Deleted old backup: $($OldBackup.Name)"
    }
    Write-Log "Cleaned up $($OldBackups.Count) old backup(s)"
}
else {
    Write-Log "No old backups to clean up"
}

# Summary
$BackupCount = (Get-ChildItem -Path $BackupPath -Filter "ruff_life_*.db*").Count
$TotalSize   = (Get-ChildItem -Path $BackupPath -Filter "ruff_life_*.db*" |
                Measure-Object -Property Length -Sum).Sum / 1MB
Write-Log "Backup complete. Total backups: $BackupCount ($([math]::Round($TotalSize, 2)) MB)"
Write-Log "----------------------------------------"