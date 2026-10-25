@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-DCP-Dashboard.ps1" -OpenBrowser
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" goto :failed
exit /b 0
:failed
echo Dashboard startup failed with exit code %RC%.
echo Review the PowerShell error above. No unverified process was stopped.
pause
exit /b %RC%