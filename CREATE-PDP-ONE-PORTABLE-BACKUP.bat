@echo off
setlocal EnableExtensions
title PDP One - Portable Encrypted Backup
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\New-PDPOnePortableBackup.ps1"
set "RC=%errorlevel%"
if not "%RC%"=="0" echo Portable backup stopped safely. Existing data and backups were not deleted.
pause
exit /b %RC%
