@echo off
chcp 65001 >nul
setlocal enableextensions
cd /d "%~dp0"

set "VENV=.venv"
set "PY=%VENV%\Scripts\python.exe"

echo ============================================
echo   StockBot one-click launcher
echo   First run auto-builds the environment
echo   (takes a few minutes, needs internet)
echo   Later runs just open directly.
echo ============================================
echo.

REM --- 1. Check system Python (need 3.10+) ---
where python >nul 2>nul
if errorlevel 1 (
    echo [X] Python not found. Install Python 3.10+ :
    echo     https://www.python.org/downloads/
    echo     Tick "Add python.exe to PATH", then re-run this file.
    echo.
    pause
    exit /b 1
)
python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)"
if errorlevel 1 (
    echo [X] Python too old. Need 3.10+. Current version:
    python --version
    echo.
    pause
    exit /b 1
)

REM --- 2. Create venv on first run ---
if not exist "%PY%" (
    echo [1/3] Creating virtual environment .venv ...
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo [X] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

REM --- 3. Install deps only when requirements.txt changed ---
set "NEED_INSTALL="
if not exist "%VENV%\requirements.lock" (
    set "NEED_INSTALL=1"
) else (
    fc /b "requirements.txt" "%VENV%\requirements.lock" >nul 2>nul || set "NEED_INSTALL=1"
)
if defined NEED_INSTALL (
    echo [2/3] Installing/updating packages, please wait...
    "%PY%" -m pip install --upgrade pip
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [X] Package install failed. Check internet and retry.
        pause
        exit /b 1
    )
    copy /y "requirements.txt" "%VENV%\requirements.lock" >nul
) else (
    echo [2/3] Packages up to date, skipping install.
)

REM --- 4. Launch dashboard ---
echo [3/3] Launching dashboard... browser opens http://localhost:8501
echo       (close this window to stop the dashboard)
echo.
"%VENV%\Scripts\streamlit.exe" run dashboard/app.py --server.port 8501

pause