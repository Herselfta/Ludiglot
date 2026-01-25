# Ludiglot 一键运行脚本
# Windows PowerShell 版本

$ErrorActionPreference = "Stop"

# 适配 PowerShell 5.1 中文乱码问题
if ($PSVersionTable.PSVersion.Major -le 5) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
}

Write-Host "=== 启动 Ludiglot ===" -ForegroundColor Cyan
Write-Host ""

# 检查虚拟环境
if (-not (Test-Path ".venv")) {
    Write-Host "错误: 未找到虚拟环境 (.venv)" -ForegroundColor Red
    Write-Host "请先运行 .\setup.ps1 进行环境配置" -ForegroundColor Yellow
    exit 1
}

# 使用虚拟环境的Python
$venvPython = ".\.venv\Scripts\python.exe"

# 检查安装状态
Write-Host "检查安装状态..." -ForegroundColor Yellow
& $venvPython -c "import ludiglot" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  警告: Ludiglot 未正确安装" -ForegroundColor Yellow
    Write-Host "  正在重新安装..." -ForegroundColor Yellow
    & $venvPython -m pip install -e . --quiet
}

# 启动程序
Write-Host ""
Write-Host "启动 Ludiglot GUI..." -ForegroundColor Green
Write-Host ""
& $venvPython -m ludiglot
