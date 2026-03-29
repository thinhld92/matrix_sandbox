@echo off
cd /d "%~dp0"
setlocal

set "PYTHON_CMD="

if exist "venv\Scripts\activate.bat" (
    echo Dang kich hoat moi truong ao...
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
        echo [ERROR] Khong tim thay Python hoac venv de khoi dong he thong.
        echo Hay chay setup_venv.bat hoac cai Python 3.9+ vao PATH.
        pause
        exit /b 1
    )

    echo [INFO] Khong tim thay venv. Dang fallback sang Python global: %PYTHON_CMD%
)

echo Dang goi Quan doc Launcher...
%PYTHON_CMD% src\launcher.py

echo.
::pause
