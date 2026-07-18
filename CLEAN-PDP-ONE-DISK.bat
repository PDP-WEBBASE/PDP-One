@echo off
setlocal
title PDP One Safe Disk Cleanup

net session >nul 2>&1
if not "%errorlevel%"=="0" (
  set "PDP_ONE_CLEANER=%~f0"
  powershell -NoProfile -Command "Start-Process -FilePath $env:PDP_ONE_CLEANER -Verb RunAs"
  exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Clean-PDPOneDisk.ps1"
set "PDP_ONE_EXIT=%errorlevel%"
pause
exit /b %PDP_ONE_EXIT%
