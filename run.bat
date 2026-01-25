@echo off
chcp 65001 >nul
REM Ludiglot 一键运行脚本 (CMD 版)

echo 正在启动 Ludiglot...
echo.

powershell.exe -ExecutionPolicy Bypass -File "%~dp0run.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo 程序运行出错 (Error Level: %ERRORLEVEL%)
    pause
    exit /b %ERRORLEVEL%
)
