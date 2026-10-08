@echo off
setlocal
cd /d "%~dp0"
title WORLDFORGE - Join a friend's Wi-Fi server
where py >nul 2>nul
if not errorlevel 1 (
    py -3 scripts\join_lan.py %*
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Install Python 3.12 or newer from https://www.python.org/downloads/
        echo Then double-click Join-WORLDFORGE-LAN.bat again.
    ) else (
        python scripts\join_lan.py %*
    )
)
echo.
echo You can close this window now.
pause
