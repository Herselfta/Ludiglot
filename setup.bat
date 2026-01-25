@echo off
chcp 65001 >nul
REM Ludiglot 一键构建脚本 (CMD 版本)

echo 正在开始 Ludiglot 环境配置...
echo.

powershell.exe -ExecutionPolicy Bypass -File "%~dp0setup.ps1"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo 配置失败！
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo 配置完成，你可以运行 run.bat 启动程序。
pause
