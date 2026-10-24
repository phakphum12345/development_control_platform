@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-DCP-Dashboard.ps1"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :failed
start "" "http://127.0.0.1:8000/"
exit /b 0
:failed
echo Dashboard startup failed with exit code %RC%.
echo Review the PowerShell error above. No unverified process was stopped.
pause
exit /b %RC%