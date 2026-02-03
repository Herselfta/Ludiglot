# Ludiglot 一键构建脚本
# Windows PowerShell 版本

$ErrorActionPreference = "Stop"

# 适配 PowerShell 5.1 中文乱码问题
if ($PSVersionTable.PSVersion.Major -le 5) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
}

Write-Host "=== Ludiglot 项目环境配置 ===" -ForegroundColor Cyan
Write-Host ""

# 检查 uv
Write-Host "检查 uv..." -ForegroundColor Yellow
$uvCmd = (Get-Command uv -ErrorAction SilentlyContinue)
$uvExe = $null
$localUv = Join-Path $env:LOCALAPPDATA "uv\\bin"
$localUvExe = Join-Path $localUv "uv.exe"
if (Test-Path $localUvExe) {
    $uvExe = $localUvExe
    $env:Path = "$localUv;$env:Path"
    $uvCmd = (Get-Command uv -ErrorAction SilentlyContinue)
}
if (-not $uvCmd) {
    Write-Host "  未找到 uv，尝试使用 winget 安装..." -ForegroundColor Yellow
    $wingetCmd = (Get-Command winget -ErrorAction SilentlyContinue)
    if ($wingetCmd) {
        winget install --id Astral.Uv -e --accept-package-agreements --accept-source-agreements
    }

    $uvCmd = (Get-Command uv -ErrorAction SilentlyContinue)
    if (-not $uvCmd) {
        Write-Host "  winget 安装失败，尝试使用官方安装脚本..." -ForegroundColor Yellow
        try {
            Import-Module Microsoft.PowerShell.Security -ErrorAction SilentlyContinue | Out-Null
            & powershell -ExecutionPolicy Bypass -Command "Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression"
        } catch {
            Write-Host "  官方安装脚本失败，尝试直接下载 uv..." -ForegroundColor Yellow
            try {
                $arch = $env:PROCESSOR_ARCHITECTURE
                $zipName = "uv-x86_64-pc-windows-msvc.zip"
                if ($arch -eq "ARM64") {
                    $zipName = "uv-aarch64-pc-windows-msvc.zip"
                } elseif ($arch -eq "x86") {
                    $zipName = "uv-i686-pc-windows-msvc.zip"
                }
                $uvUrl = "https://github.com/astral-sh/uv/releases/latest/download/$zipName"
                $uvZip = Join-Path $env:TEMP "uv.zip"
                $uvDir = Join-Path $env:LOCALAPPDATA "uv\\bin"
                New-Item -ItemType Directory -Force -Path $uvDir | Out-Null
                & curl.exe -L $uvUrl -o $uvZip
                Expand-Archive -Path $uvZip -DestinationPath $uvDir -Force
                Remove-Item -Force $uvZip -ErrorAction SilentlyContinue
            } catch {
                Write-Host "  错误: uv 安装失败" -ForegroundColor Red
                Write-Host "  请手动安装 uv: https://astral.sh/uv" -ForegroundColor Yellow
                exit 1
            }
        }
    }

    $uvCmd = (Get-Command uv -ErrorAction SilentlyContinue)
    if (-not $uvCmd) {
        $localUv = Join-Path $env:LOCALAPPDATA "uv\\bin"
        $localUvExe = Join-Path $localUv "uv.exe"
        if (Test-Path $localUvExe) {
            $uvExe = $localUvExe
            $env:Path = "$localUv;$env:Path"
        }
        $uvCmd = (Get-Command uv -ErrorAction SilentlyContinue)
    }
    if (-not $uvCmd -and -not $uvExe) {
        Write-Host "  错误: uv 安装失败或未加入 PATH" -ForegroundColor Red
        exit 1
    }
}
if (-not $uvExe) {
    $uvExe = $uvCmd.Source
}

# 检查/准备 Python（由 uv 负责）
Write-Host "检查 Python 3.12..." -ForegroundColor Yellow
try {
    & $uvExe python install 3.12 --quiet | Out-Null
    $uvVersion = & $uvExe --version 2>&1
    Write-Host "  发现: $uvVersion" -ForegroundColor Green
} catch {
    Write-Host "  错误: uv 无法准备 Python 3.12" -ForegroundColor Red
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
        & $uvExe venv -p 3.12 .venv
    }
} else {
    Write-Host "  创建虚拟环境..." -ForegroundColor Yellow
    & $uvExe venv -p 3.12 .venv
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
& $uvExe pip install --python $venvPython --upgrade pip --quiet

# 安装依赖
Write-Host ""
Write-Host "安装项目依赖..." -ForegroundColor Yellow
if (Test-Path "requirements.txt") {
    & $uvExe pip install --python $venvPython -r requirements.txt
}
 else {
    Write-Host "  警告: 未找到 requirements.txt，跳过依赖安装" -ForegroundColor Yellow
}

# 安装项目（开发模式）
Write-Host ""
Write-Host "安装 Ludiglot（开发模式）..." -ForegroundColor Yellow
& $uvExe pip install --python $venvPython -e .[paddle]

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
    & $venvPython -c "import winrt.windows.media.ocr" 2>$null
    Write-Host " 已安装 (推荐)" -ForegroundColor Green
} catch {
    Write-Host " 未安装" -ForegroundColor Yellow
    Write-Host "    如果您使用的是 Windows 10/11，强烈建议安装: pip install winrt-Windows.Media.Ocr" -ForegroundColor Gray
}

# 检查 PaddleOCR 支持
Write-Host "  - PaddleOCR..." -NoNewline
try {
    & $venvPython -c "import paddleocr" 2>$null
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
