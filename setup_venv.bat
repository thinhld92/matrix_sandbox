@echo off
cd /d "%~dp0"
title MATRIX SANDBOX - SETUP VENV
setlocal

set "PYTHON_CMD="

where python >nul 2>nul
if %errorlevel%==0 set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
    where py >nul 2>nul
    if %errorlevel%==0 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    echo [ERROR] Khong tim thay Python trong PATH.
    echo Hay cai Python 3.9+ roi chay lai file nay.
    pause
    exit /b 1
)

echo ============================================
echo   MATRIX SANDBOX - TAO VENV VA CAI GOI
echo ============================================
echo.
echo Dang dung: %PYTHON_CMD%
echo.

if exist "venv\Scripts\python.exe" (
    echo [INFO] Da ton tai venv. Bo qua buoc tao moi.
) else (
    echo [1/4] Dang tao venv...
    %PYTHON_CMD% -m venv venv
    if errorlevel 1 (
        echo [ERROR] Tao venv that bai.
        pause
        exit /b 1
    )
)

echo [2/4] Dang kich hoat venv...
call venv\Scripts\activate
if errorlevel 1 (
    echo [ERROR] Khong the kich hoat venv.
    pause
    exit /b 1
)

echo [3/4] Dang nang cap pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Nang cap pip that bai.
    pause
    exit /b 1
)

echo [4/4] Dang cai dependencies tu requirements.txt...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Cai dependencies that bai.
    pause
    exit /b 1
)

echo.
echo [OK] Hoan tat. Moi truong ao da san sang.
echo Lan sau co the chay start_bots.bat de khoi dong he thong.
echo.
pause
