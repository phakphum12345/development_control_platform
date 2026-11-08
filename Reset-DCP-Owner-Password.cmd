@echo off
setlocal
cd /d "%~dp0"
py -3 tools\\reset_owner_password.py
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo Owner password reset did not complete. Review the message above.
) else (
  echo Owner password reset completed.
)
pause
exit /b %RC%
