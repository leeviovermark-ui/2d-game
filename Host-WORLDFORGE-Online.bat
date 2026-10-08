@echo off
setlocal
cd /d "%~dp0"
title WORLDFORGE - Host for friends online
where py >nul 2>nul
if not errorlevel 1 (
    py -3 scripts\host_online.py %*
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Install Python 3.12 or newer from https://www.python.org/downloads/
        echo Then double-click Host-WORLDFORGE-Online.bat again.
    ) else (
        python scripts\host_online.py %*
    )
)
echo.
echo You can close this window now.
pause
