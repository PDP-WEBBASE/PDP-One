@echo off
chcp 65001 >nul
cd /d "%~dp0"

if /I not "%~1"=="--elevated" (
    echo Requesting administrator access...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList '--elevated' -Verb RunAs"
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\Install-PDPOne.ps1"
pause
