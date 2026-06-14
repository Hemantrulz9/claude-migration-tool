@echo off
title Claude Migration Tool
rem Single double-click launcher. Self-elevates to administrator (one UAC prompt),
rem then runs the single-file .exe if present, otherwise runs the Python program.

net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"

if exist "dist\Claude-Migrate.exe" (
    "dist\Claude-Migrate.exe"
    goto :end
)
if exist "Claude-Migrate.exe" (
    "Claude-Migrate.exe"
    goto :end
)

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo Python 3.10+ is required but was not found.
    echo Install it from https://www.python.org/downloads/ then run this again.
    echo.
    pause
    exit /b
)

python main.py

:end
pause
