@echo off
setlocal
title PDP One Deployment Agent Bootstrap

fltmc >nul 2>&1
if not "%errorlevel%"=="0" (
  echo Requesting administrator permission...
  powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo.
echo PDP One Deployment Agent bootstrap

echo This updates only the local deployment tool.
echo It does not change the web application, Docker, database, volumes, backups, Tailscale, .env, or tokens.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\Bootstrap-PDPOneDeploymentAgent.ps1"
set RC=%errorlevel%

echo.
if "%RC%"=="0" (
  echo Bootstrap completed successfully.
  echo Send PDP-ONE-AGENT-BOOTSTRAP-REPORT.json from your Desktop to the project chat.
) else (
  echo Bootstrap failed. The previous deployment script was restored when possible.
  echo Send PDP-ONE-AGENT-BOOTSTRAP-REPORT.json from your Desktop to the project chat.
)
echo.
pause
exit /b %RC%
