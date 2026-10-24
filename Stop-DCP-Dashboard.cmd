@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Stop-DCP-Dashboard.ps1"
set "RC=%ERRORLEVEL%"
if "%RC%"=="4" goto :not_owned
if not "%RC%"=="0" goto :failed
echo Launcher-owned Dashboard server stopped, or was already stopped.
exit /b 0
:not_owned
echo No launcher-owned server was recorded. No process was stopped.
exit /b 0
:failed
echo STOP REFUSED or failed. No unverified process was intentionally stopped.
pause
exit /b %RC%