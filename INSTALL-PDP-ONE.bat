@echo off
chcp 65001 >nul
cd /d "%~dp0"

if /I not "%~1"=="--elevated" (
    echo Requesting administrator access...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList '--elevated' -Verb RunAs"
    exit /b
)

findstr /c:"$InstallerVersion = \"2026.07.19.18\"" ".\scripts\windows\Install-PDPOne.ps1" >nul 2>&1
if not "%errorlevel%"=="0" (
    echo This is an outdated or incomplete PDP One installer package.
    echo Download and extract the latest main branch before running the installer.
    pause
    exit /b 2
)

powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\windows\Install-PDPOne.ps1"
pause
