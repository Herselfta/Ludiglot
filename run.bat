@echo off
REM Ludiglot 一键运行脚本 (CMD 版本)
REM 简单启动 PowerShell 脚本

powershell.exe -ExecutionPolicy Bypass -File "%~dp0run.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Run failed!
    pause
    exit /b %ERRORLEVEL%
)
