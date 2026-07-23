@echo off
setlocal
title PDP One Emergency Start and Repair
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  set "PDP_ONE_EMERGENCY=%~f0"
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath $env:PDP_ONE_EMERGENCY -Verb RunAs"
  exit /b
)
cd /d "%~dp0"
echo Starting PDP One and repairing connectivity. No data, volume, token, or database record will be deleted.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Start-PDPOne.ps1" -OpenLocalPage -ForceTunnelRepair
set "PDP_ONE_EXIT=%errorlevel%"
if not "%PDP_ONE_EXIT%"=="0" (
  echo.
  echo Emergency startup did not fully restore the public connection.
  echo A safe diagnostic file has been created as PDP-ONE-LAST-DIAGNOSTICS.txt.
  if exist "%~dp0PDP-ONE-LAST-DIAGNOSTICS.txt" start "" notepad.exe "%~dp0PDP-ONE-LAST-DIAGNOSTICS.txt"
  pause
)
exit /b %PDP_ONE_EXIT%
