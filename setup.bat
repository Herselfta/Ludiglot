@echo off
REM Ludiglot 一键构建脚本 (CMD 版本)
REM 简单启动 PowerShell 脚本

echo Starting Ludiglot setup...
echo.

powershell.exe -ExecutionPolicy Bypass -File "%~dp0setup.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Setup failed!
    pause
    exit /b %ERRORLEVEL%
)

echo.
pause
