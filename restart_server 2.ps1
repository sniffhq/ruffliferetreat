# Ruff Life Retreat - Safe Server Restart Script
# Run this as Administrator in PowerShell

Write-Host "`n" + "="*70 -ForegroundColor Cyan
Write-Host "Ruff Life Retreat - Safe Server Restart" -ForegroundColor Cyan
Write-Host "="*70 -ForegroundColor Cyan

$appRoot = "C:\RuffLifeRetreat"

# STEP 1: Kill all Python/Waitress processes
Write-Host "`n[STEP 1/5] Killing all Waitress processes..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "✓ Python processes stopped" -ForegroundColor Green
Start-Sleep -Seconds 2

# STEP 2: Clear Python cache
Write-Host "`n[STEP 2/5] Clearing Python cache..." -ForegroundColor Yellow
$cacheDirs = @(
    "$appRoot\app\__pycache__",
    "$appRoot\app\routes\__pycache__",
    "$appRoot\app\templates\__pycache__",
    "$appRoot\.pytest_cache"
)

foreach ($dir in $cacheDirs) {
    if (Test-Path $dir) {
        Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "✓ Deleted: $dir" -ForegroundColor Green
    }
}

# STEP 3: Verify template changes
Write-Host "`n[STEP 3/5] Verifying template changes..." -ForegroundColor Yellow
$templatePath = "$appRoot\app\templates\admin\daycare_dashboard.html"

if (Test-Path $templatePath) {
    $content = Get-Content $templatePath -Raw
    
    if ($content -match "Waitlist Summary") {
        Write-Host "✓ Template has new Waitlist Summary section" -ForegroundColor Green
    } else {
        Write-Host "✗ WARNING: Template does NOT have Waitlist Summary" -ForegroundColor Red
    }
    
    if ($content -match "TEST") {
        Write-Host "✓ TEST marker found in template" -ForegroundColor Green
    }
} else {
    Write-Host "✗ Template file not found: $templatePath" -ForegroundColor Red
}

# STEP 4: Verify admin.py changes
Write-Host "`n[STEP 4/5] Verifying admin.py changes..." -ForegroundColor Yellow
$adminPath = "$appRoot\app\routes\admin.py"

if (Test-Path $adminPath) {
    $content = Get-Content $adminPath -Raw
    
    if ($content -match "contacted_waitlist" -and $content -match "all_waitlist") {
        Write-Host "✓ admin.py has new waitlist fetching code" -ForegroundColor Green
    } else {
        Write-Host "✗ WARNING: admin.py does NOT have new waitlist code" -ForegroundColor Red
    }
} else {
    Write-Host "✗ admin.py not found: $adminPath" -ForegroundColor Red
}

# STEP 5: Start Waitress
Write-Host "`n[STEP 5/5] Starting Waitress server..." -ForegroundColor Yellow
Write-Host "="*70 -ForegroundColor Cyan

Set-Location $appRoot

Write-Host "`nWaitress is starting on http://localhost:8000" -ForegroundColor Cyan
Write-Host "Access via: https://rufflife.app (IIS handles HTTPS)" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop the server`n" -ForegroundColor Cyan

& "$appRoot\venv\Scripts\python.exe" run_production.py