@echo off
setlocal
title PDP One Safe Diagnostics
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  set "PDP_ONE_DIAG=%~f0"
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath $env:PDP_ONE_DIAG -Verb RunAs"
  exit /b
)
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\New-PDPOneDiagnostics.ps1" -FailureMessage "Manual diagnostic requested by user" -Stage "manual" -OpenReport
set "PDP_ONE_EXIT=%errorlevel%"
if not "%PDP_ONE_EXIT%"=="0" pause
exit /b %PDP_ONE_EXIT%
