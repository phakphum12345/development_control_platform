@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-DCP-Gateway-Runner.ps1" %*
exit /b %ERRORLEVEL%
