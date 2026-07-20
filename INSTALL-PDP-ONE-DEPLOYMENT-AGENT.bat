@echo off
setlocal
title PDP One Local Deployment Agent Setup
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  set "PDP_ONE_AGENT_SETUP=%~f0"
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath $env:PDP_ONE_AGENT_SETUP -Verb RunAs"
  exit /b
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Install-PDPOneDeploymentAgent.ps1"
set "PDP_ONE_EXIT=%errorlevel%"
pause
exit /b %PDP_ONE_EXIT%
