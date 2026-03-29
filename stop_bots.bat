@echo off
cd /d "%~dp0"
title MATRIX SANDBOX - LENH RUT QUAN
setlocal

set "PYTHON_CMD="

echo.
echo ============================================
echo   DANG HA LENH RUT QUAN TOAN BO...
echo ============================================
echo.

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate
    if errorlevel 1 (
        echo [ERROR] Khong the kich hoat venv.
        pause
        exit /b 1
    )
    set "PYTHON_CMD=python"
) else (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"

    if not defined PYTHON_CMD (
        where py >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=py -3"
    )

    if not defined PYTHON_CMD (
        echo [ERROR] Khong tim thay Python hoac venv de gui lenh shutdown.
        pause
        exit /b 1
    )

    echo [INFO] Khong tim thay venv. Dang fallback sang Python global: %PYTHON_CMD%
)

%PYTHON_CMD% -c "import redis, json; r = redis.Redis(**json.load(open('config.json'))['redis'], decode_responses=True); r.setex('SIGNAL:SHUTDOWN', 30, '1'); print('Da gui tin hieu tat may qua Redis!')"

echo Cho 10 giay de cac process tu tat an toan...
timeout /t 10 /nobreak >nul

%PYTHON_CMD% -c "import redis, json; r = redis.Redis(**json.load(open('config.json'))['redis'], decode_responses=True); r.delete('SIGNAL:SHUTDOWN'); print('Da don dep tin hieu shutdown.')"

taskkill /F /FI "WINDOWTITLE eq *MATRIX SANDBOX*" 2>nul
taskkill /F /FI "WINDOWTITLE eq *SANDBOX*" 2>nul
taskkill /F /FI "WINDOWTITLE eq *TELEGRAM*" 2>nul

echo.
echo Tat ca quan doan da rut lui an toan!
echo.
pause
