# Ludiglot 一键构建脚本
# Windows PowerShell 版本

$ErrorActionPreference = "Stop"

# 适配 PowerShell 5.1 中文乱码问题
if ($PSVersionTable.PSVersion.Major -le 5) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
}

Write-Host "=== Ludiglot 项目环境配置 ===" -ForegroundColor Cyan
Write-Host ""

# 检查 Python 版本
Write-Host "检查 Python 版本..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  发现: $pythonVersion" -ForegroundColor Green
    
    # 验证 Python 版本 >= 3.10
    if ($pythonVersion -match "Python (\d+)\.(\d+)") {
        $major = [int]$matches[1]
        $minor = [int]$matches[2]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
            Write-Host "  错误: 需要 Python 3.10 或更高版本" -ForegroundColor Red
            exit 1
        }
    }
} catch {
    Write-Host "  错误: 未找到 Python，请安装 Python 3.10+" -ForegroundColor Red
    Write-Host "  下载地址: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# 检查虚拟环境
Write-Host ""
Write-Host "检查虚拟环境..." -ForegroundColor Yellow
if (Test-Path ".venv") {
    Write-Host "  发现现有虚拟环境: .venv" -ForegroundColor Green
    $response = Read-Host "  是否重新创建? (y/N)"
    if ($response -eq "y" -or $response -eq "Y") {
        Write-Host "  删除现有虚拟环境..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force .venv
        Write-Host "  创建新虚拟环境..." -ForegroundColor Yellow
        python -m venv .venv
    }
} else {
    Write-Host "  创建虚拟环境..." -ForegroundColor Yellow
    python -m venv .venv
}

# 激活虚拟环境
Write-Host ""
Write-Host "激活虚拟环境..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# 定义虚拟环境 Python 路径
$venvPython = ".\.venv\Scripts\python.exe"

# 升级 pip (仅当虚拟环境创建后执行一次，或使用静默模式)
Write-Host ""
Write-Host "检查并升级 pip..." -ForegroundColor Yellow
& $venvPython -m pip install --upgrade pip --quiet

# 安装依赖
Write-Host ""
Write-Host "安装项目依赖..." -ForegroundColor Yellow
if (Test-Path "requirements.txt") {
    & $venvPython -m pip install -r requirements.txt
}
 else {
    Write-Host "  警告: 未找到 requirements.txt，跳过依赖安装" -ForegroundColor Yellow
}

# 安装项目（开发模式）
Write-Host ""
Write-Host "安装 Ludiglot（开发模式）..." -ForegroundColor Yellow
& $venvPython -m pip install -e .

# 创建必要目录
Write-Host ""
Write-Host "创建必要目录..." -ForegroundColor Yellow
$folders = @("cache", "cache/audio", "data", "config")
foreach ($f in $folders) {
    if (-not (Test-Path $f)) {
        New-Item -ItemType Directory $f | Out-Null
        Write-Host "  创建目录: $f" -ForegroundColor Green
    }
}

# 检查可选依赖
Write-Host ""
Write-Host "检查项目数据..." -ForegroundColor Yellow

# 检查数据目录
# 自动生成配置文件
if (-not (Test-Path "config/settings.json")) {
    if (Test-Path "config/settings.example.json") {
        Copy-Item "config/settings.example.json" "config/settings.json"
        Write-Host "  已自动生成配置文件: config/settings.json" -ForegroundColor Green
    } else {
        Write-Host "  未找到 config/settings.example.json，无法自动生成配置" -ForegroundColor Red
    }
}

# 检查数据目录配置
if (Test-Path "config/settings.json") {
    try {
        $config = Get-Content "config/settings.json" | ConvertFrom-Json
        $dataRoot = $config.data_root
        if (-not (Test-Path $dataRoot)) {
            Write-Host "  注意: 配置文件中的 data_root 路径指向空 ($dataRoot)" -ForegroundColor Yellow
            Write-Host "  如果尚未下载 WutheringData，运行程序时会提示您自动下载。" -ForegroundColor Gray
        } else {
            Write-Host "  数据目录配置有效: $dataRoot" -ForegroundColor Green
        }
    } catch {
        Write-Host "  警告: 配置文件格式可能有误" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "检查可选扩展..." -ForegroundColor Yellow

# 检查 Windows OCR 支持
Write-Host "  - Windows OCR (WinRT)..." -NoNewline
try {
    python -c "import winrt.windows.media.ocr" 2>$null
    Write-Host " 已安装 (推荐)" -ForegroundColor Green
} catch {
    Write-Host " 未安装" -ForegroundColor Yellow
    Write-Host "    如果您使用的是 Windows 10/11，强烈建议安装: pip install winrt-Windows.Media.Ocr" -ForegroundColor Gray
}

# 检查 PaddleOCR 支持
Write-Host "  - PaddleOCR..." -NoNewline
try {
    python -c "import paddleocr" 2>$null
    Write-Host " 已安装" -ForegroundColor Green
} catch {
    Write-Host " 未安装 (可选)" -ForegroundColor Cyan
    Write-Host "    如需更高识别率且不介意性能，可安装: pip install ludiglot[paddle]" -ForegroundColor Gray
}

Write-Host ""
Write-Host "检查第三方工具 (可选，用于音频功能)..." -ForegroundColor Yellow

# 检查 FModel
if (-not (Test-Path "tools/FModel.exe")) {
    Write-Host "  - FModel.exe..." -NoNewline
    Write-Host " 未找到" -ForegroundColor Yellow
    Write-Host "    用于提取游戏资源，请从 https://fmodel.app/ 下载并放置到 tools/ 目录" -ForegroundColor Gray
    Write-Host "    详见: tools/README.md" -ForegroundColor Gray
} else {
    Write-Host "  - FModel.exe..." -NoNewline
    Write-Host " 已找到" -ForegroundColor Green
}

# 检查 vgmstream
$vgmstreamPaths = @(
    "tools/vgmstream/vgmstream-cli.exe",
    "tools/vgmstream/vgmstream.exe",
    "tools/vgmstream/test.exe"
)
$vgmstreamFound = $false
foreach ($path in $vgmstreamPaths) {
    if (Test-Path $path) {
        $vgmstreamFound = $true
        break
    }
}
if (-not $vgmstreamFound) {
    Write-Host "  - vgmstream..." -NoNewline
    Write-Host " 未找到" -ForegroundColor Yellow
    Write-Host "    用于音频转换，请从 https://github.com/vgmstream/vgmstream 下载并解压到 tools/vgmstream/" -ForegroundColor Gray
} else {
    Write-Host "  - vgmstream..." -NoNewline
    Write-Host " 已找到" -ForegroundColor Green
}

# 完成
Write-Host ""
Write-Host "=== 环境配置完成! ===" -ForegroundColor Green
Write-Host ""
Write-Host "下一步:" -ForegroundColor Cyan
Write-Host "  1. 运行程序: .\run.ps1" -ForegroundColor White
Write-Host "  2. 或手动运行: .\.venv\Scripts\Activate.ps1 && python -m ludiglot" -ForegroundColor White
Write-Host ""
