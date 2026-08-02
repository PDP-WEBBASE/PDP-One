@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Repair-PDPOneMcpAfterIssue43.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo Repair failed with exit code %RC%.
if "%RC%"=="0" echo Repair completed successfully.
pause
exit /b %RC%
