@echo off
setlocal
title PDP One MCP Token Rotation
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  set "PDP_ONE_ROTATE=%~f0"
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath $env:PDP_ONE_ROTATE -Verb RunAs"
  exit /b
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Rotate-PDPOneMcpToken.ps1"
set "PDP_ONE_EXIT=%errorlevel%"
pause
exit /b %PDP_ONE_EXIT%
