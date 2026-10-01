@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows.ps1" -Mode Start
set "ORBIT_EXIT=%ERRORLEVEL%"
if not "%ORBIT_EXIT%"=="0" pause
exit /b %ORBIT_EXIT%
