@echo off
setlocal
title PDP One Safe Disk Cleanup

net session >nul 2>&1
if not "%errorlevel%"=="0" (
  set "PDP_ONE_CLEANER=%~f0"
  powershell -NoProfile -Command "Start-Process -FilePath $env:PDP_ONE_CLEANER -Verb RunAs"
  exit /b
)

echo Cleanup package: %~dp0
findstr /c:"PDP One safe disk cleanup 2026.07.18.6" "%~dp0scripts\windows\Clean-PDPOneDisk.ps1" >nul 2>&1
if not "%errorlevel%"=="0" (
  echo This is an outdated or incomplete PDP One cleanup package.
  echo Download and extract the latest main branch, then run CLEAN-PDP-ONE-DISK.bat there.
  pause
  exit /b 2
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Clean-PDPOneDisk.ps1" -CurrentSourceRoot "%~dp0." -CompactWsl
set "PDP_ONE_EXIT=%errorlevel%"
pause
exit /b %PDP_ONE_EXIT%
