@echo off
setlocal
title PDP One Safe Stop
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Stop-PDPOne.ps1"
set "PDP_ONE_EXIT=%errorlevel%"
if not "%PDP_ONE_EXIT%"=="0" pause
exit /b %PDP_ONE_EXIT%
