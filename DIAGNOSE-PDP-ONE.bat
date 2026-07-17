@echo off
chcp 65001 >nul
cd /d "%~dp0"

if /I not "%~1"=="--elevated" (
    echo Requesting administrator access for read-only diagnostics...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList '--elevated' -Verb RunAs"
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\Diagnose-PDPOne.ps1"
pause
