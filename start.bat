@echo off
chcp 65001 >nul
title SmarType

REM === If not admin, relaunch as admin ===
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
echo Starting SmarType...
python dictation.py
if %errorlevel% neq 0 (
    echo [ERROR] check userdata\debug.log
    pause
)
