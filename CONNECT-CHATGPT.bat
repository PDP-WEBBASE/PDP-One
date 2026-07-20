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
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Connect-PDPOneChatGPT.ps1"
if errorlevel 1 pause
