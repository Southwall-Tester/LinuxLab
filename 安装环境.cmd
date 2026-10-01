@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows.ps1" -Mode Setup
set "ORBIT_EXIT=%ERRORLEVEL%"
pause
exit /b %ORBIT_EXIT%
