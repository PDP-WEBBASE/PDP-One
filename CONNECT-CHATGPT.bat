@echo off
setlocal
title PDP One ChatGPT Connection

net session >nul 2>&1
if not "%errorlevel%"=="0" (
  set "PDP_ONE_CONNECTOR=%~f0"
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath $env:PDP_ONE_CONNECTOR -Verb RunAs"
  exit /b
)

cd /d "%~dp0"
echo Clearing the Windows DNS cache...
ipconfig /flushdns >nul 2>&1

if exist "%~dp0PDP-ONE-CHATGPT-CONNECTION.txt" (
  echo Existing stable connector configuration detected.
  echo Starting PDP One and repairing the public connection without changing tokens or Windows DNS...
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Start-PDPOne.ps1" -OpenLocalPage -ForceTunnelRepair
) else (
  echo First-time connector setup detected.
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Connect-PDPOneChatGPT.ps1"
)

set "PDP_ONE_EXIT=%errorlevel%"
if not "%PDP_ONE_EXIT%"=="0" (
  echo.
  echo PDP One did not complete the connection sequence.
  echo Use PDP-ONE-EMERGENCY-START.bat or send PDP-ONE-LAST-DIAGNOSTICS.txt for review.
  pause
)
exit /b %PDP_ONE_EXIT%
