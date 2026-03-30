@echo off
chcp 65001 >nul
title 快打 SmarType - 管理介面
cd /d "%~dp0"
python dashboard.py
