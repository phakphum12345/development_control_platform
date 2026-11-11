@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" ( echo Usage: Check-DCP-Local-Runner.cmd OWNER/PRIVATE-REPOSITORY & exit /b 2 )
py -3 -m tools.local_runner_manager doctor --repository "%~1"
exit /b %errorlevel%
