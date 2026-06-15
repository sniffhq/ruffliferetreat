@echo off
REM ============================================================================
REM Ruff Life Retreat - Start Both HTTP and HTTPS Servers
REM This batch file starts both the redirect server (port 80) and 
REM production server (port 443) in separate windows
REM
REM NOTE: This must be run as Administrator!
REM ============================================================================

REM Check for administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo ============================================================================
    echo ERROR: This script must be run as Administrator!
    echo ============================================================================
    echo.
    echo Right-click on this file and select "Run as Administrator"
    echo.
    pause
    exit /b 1
)

setlocal enabledelayedexpansion

set APPDIR=C:\RuffLifeRetreat
set PYTHON=python

echo.
echo ============================================================================
echo Ruff Life Retreat - Starting Web Servers
echo ============================================================================
echo.

REM Check if app directory exists
if not exist "%APPDIR%" (
    echo ERROR: Application directory not found: %APPDIR%
    echo Please update APPDIR in this script to match your installation.
    pause
    exit /b 1
)

REM Check if Python is available
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Python not found in PATH
    echo Please install Python or add it to your PATH
    pause
    exit /b 1
)

REM Check if required files exist
if not exist "%APPDIR%\run_http_redirect.py" (
    echo ERROR: run_http_redirect.py not found in %APPDIR%
    pause
    exit /b 1
)

if not exist "%APPDIR%\run_production.py" (
    echo ERROR: run_production.py not found in %APPDIR%
    pause
    exit /b 1
)

echo.
echo [1/2] Starting HTTP Redirect Server (Port 80)...
echo       This redirects all HTTP traffic to HTTPS
echo.
start "Ruff Life Retreat - HTTP Redirect (Port 80)" cmd /k ^
    python "%APPDIR%\run_http_redirect.py"

REM Give the first server a moment to start
timeout /t 2 /nobreak

echo.
echo [2/2] Starting HTTPS Production Server (Port 443)...
echo       This serves your Ruff Life Retreat application
echo.
start "Ruff Life Retreat - HTTPS Production (Port 443)" cmd /k ^
    python "%APPDIR%\run_production.py"

echo.
echo ============================================================================
echo Servers Started Successfully!
echo ============================================================================
echo.
echo Access your application at: https://rufflife.app
echo.
echo Two windows should have opened:
echo   1. HTTP Redirect Server (Port 80)
echo   2. HTTPS Production Server (Port 443)
echo.
echo To stop the servers:
echo   - Close each window individually
echo   - Or press Ctrl+C in each window
echo.
echo ============================================================================
echo.

REM Keep this window open for information
echo Press any key to close this window...
pause >nul