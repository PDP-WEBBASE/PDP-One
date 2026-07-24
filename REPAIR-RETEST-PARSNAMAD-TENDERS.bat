@echo off
setlocal
cd /d "%~dp0"
title PDP One - Pars Namad Tender Repair and Retest

echo.
echo PDP One - Pars Namad Tender Repair and Retest
echo ------------------------------------------------
echo This tool backs up PostgreSQL first.
echo It removes only new records from the incorrect controlled test.
echo Selected or protected records are never deleted.
echo It then tests five pages from the corrected tender route.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Repair-Retest-ParsnamadTenders.ps1" -Pages 5
set "ExitCode=%ERRORLEVEL%"

if not "%ExitCode%"=="0" (
  echo.
  echo The repair or retest did not complete successfully.
  echo Upload the generated PDP-ONE-PARSNAMAD-TENDER-REPAIR ZIP.
  pause
  exit /b %ExitCode%
)

endlocal
