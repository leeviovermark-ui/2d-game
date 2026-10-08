@echo off
setlocal
cd /d "%~dp0"
title WORLDFORGE - Host for friends on your Wi-Fi
where py >nul 2>nul
if not errorlevel 1 (
    py -3 scripts\play.py --host 0.0.0.0 %*
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Install Python 3.12 or newer from https://www.python.org/downloads/
        echo Then double-click Host-WORLDFORGE-LAN.bat again.
    ) else (
        python scripts\play.py --host 0.0.0.0 %*
    )
)
echo.
echo You can close this window now.
pause
