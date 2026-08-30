@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-app.ps1" %*
set "RUN_APP_EXIT=%ERRORLEVEL%"
if not "%RUN_APP_EXIT%"=="0" (
  echo.
  echo App startup failed. Review the message above.
  pause
)
exit /b %RUN_APP_EXIT%
