@echo off
setlocal
cd /d "%~dp0"
title PDP One - Hezareh and Pars Namad Connector Test

echo.
echo PDP One - Hezareh and Pars Namad Connector Test
echo -------------------------------------------------
echo Four connectors will be tested.
echo Five pages will be requested for each connector.
echo SETAD is not included in this test.
echo Detail extraction and ChatGPT analysis are disabled.
echo A PostgreSQL backup is created before migration.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Test-HezarehParsnamadConnectors.ps1" -Pages 5
set "ExitCode=%ERRORLEVEL%"

if not "%ExitCode%"=="0" (
  echo.
  echo The connector test did not complete successfully.
  echo Upload the generated PDP-ONE-HEZAREH-PARSNAMAD-LIVE-TEST ZIP to the ChatGPT conversation.
  pause
  exit /b %ExitCode%
)

endlocal
