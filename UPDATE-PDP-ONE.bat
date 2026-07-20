@echo off
setlocal
title PDP One Updater

net session >nul 2>&1
if not "%errorlevel%"=="0" (
  set "PDP_ONE_UPDATER=%~f0"
  powershell -NoProfile -Command "Start-Process -FilePath $env:PDP_ONE_UPDATER -Verb RunAs"
  exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Update-PDPOne.ps1"
set "PDP_ONE_EXIT=%errorlevel%"

if not "%PDP_ONE_EXIT%"=="0" (
  echo.
  echo PDP One update failed. Review the message above.
)

pause
exit /b %PDP_ONE_EXIT%

