@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup-DCP-Local.ps1"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo DCP local setup failed with exit code %RC%.
  pause
) else (
  echo.
  echo Setup checks completed successfully.
  pause
)
exit /b %RC%
