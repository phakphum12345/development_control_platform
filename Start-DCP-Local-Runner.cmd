@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 ( echo Python Launcher py.exe was not found. & exit /b 1 )
if "%~1"=="" ( echo Usage: Start-DCP-Local-Runner.cmd OWNER/PRIVATE-REPOSITORY & exit /b 2 )
py -3 -m tools.local_runner_manager start --repository "%~1"
exit /b %errorlevel%
