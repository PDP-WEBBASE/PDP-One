@echo off
setlocal
title PDP One Stable Startup
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  set "PDP_ONE_START=%~f0"
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath $env:PDP_ONE_START -Verb RunAs"
  exit /b
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Start-PDPOne.ps1"
set "PDP_ONE_EXIT=%errorlevel%"
if not "%PDP_ONE_EXIT%"=="0" pause
exit /b %PDP_ONE_EXIT%
