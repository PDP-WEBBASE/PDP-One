@echo off
setlocal
cd /d "%~dp0"
title PDP One - SETAD Connector Live Test

echo.
echo PDP One - SETAD Connector Live Test
echo ------------------------------------
echo This test activates the approved public SETAD connectors.
echo It tests two pages per connector without login, captcha bypass or detail extraction.
echo A PostgreSQL backup is created before migration.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Test-SetadConnectors.ps1" -Pages 2
set "ExitCode=%ERRORLEVEL%"

if not "%ExitCode%"=="0" (
  echo.
  echo The SETAD test did not complete successfully.
  echo Upload the generated PDP-ONE-SETAD-LIVE-TEST ZIP to the ChatGPT conversation.
  pause
  exit /b %ExitCode%
)

endlocal
