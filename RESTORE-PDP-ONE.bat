@echo off
setlocal EnableExtensions
title PDP One - One-File Portable Restore
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Restore-PDPOnePortableBackup.ps1"
set "RC=%errorlevel%"
if not "%RC%"=="0" echo Restore stopped safely. Review PDP-ONE-PORTABLE-RESTORE-REPORT.json on the Desktop.
pause
exit /b %RC%
