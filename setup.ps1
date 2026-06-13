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

function Use-UvPath {
    param([string]$Dir)

    $candidate = Join-Path $Dir "uv.exe"
    if (-not (Test-Path $candidate)) {
        return $false
    }

    $script:uvExe = $candidate
    $env:Path = "$Dir;$env:Path"
    $script:uvCmd = (Get-Command uv -ErrorAction SilentlyContinue)
    return $true
}

# 优先检查官方标准的 .local\bin 目录
$localBinUv = Join-Path $env:USERPROFILE ".local\\bin"
[void](Use-UvPath $localBinUv)

# 其次兜底检查旧的 AppData\Local\uv 目录（做兼容）
if (-not $uvExe) {
    $oldUv = Join-Path $env:LOCALAPPDATA "uv\\bin"
    [void](Use-UvPath $oldUv)
}

if (-not $uvCmd -and -not $uvExe) {
    Write-Host "  未找到 uv，优先尝试使用官方安装脚本..." -ForegroundColor Yellow
    try {
        Import-Module Microsoft.PowerShell.Security -ErrorAction SilentlyContinue | Out-Null
        & powershell -ExecutionPolicy Bypass -Command "Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression"
        
        # 官方脚本默认安装在 .local\bin
        [void](Use-UvPath $localBinUv)
    } catch {
        Write-Host "  官方安装脚本失败，尝试使用 winget 安装..." -ForegroundColor Yellow
        $wingetCmd = (Get-Command winget -ErrorAction SilentlyContinue)
        if ($wingetCmd) {
            winget install --id Astral.Uv -e --accept-package-agreements --accept-source-agreements
        }
    }

    $uvCmd = (Get-Command uv -ErrorAction SilentlyContinue)
    if (-not $uvCmd -and -not $uvExe) {
        Write-Host "  依然未找到 uv，尝试直接下载官方 Release 压缩包..." -ForegroundColor Yellow
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
            # 统一直接下载释放到标准的 .local\bin
            New-Item -ItemType Directory -Force -Path $localBinUv | Out-Null
            & curl.exe -L $uvUrl -o $uvZip
            Expand-Archive -Path $uvZip -DestinationPath $localBinUv -Force
            Remove-Item -Force $uvZip -ErrorAction SilentlyContinue
            
            [void](Use-UvPath $localBinUv)
        } catch {
            Write-Host "  错误: uv 自动安装失败" -ForegroundColor Red
            Write-Host "  请手动安装 uv: https://astral.sh/uv" -ForegroundColor Yellow
            exit 1
        }
    }

    $uvCmd = (Get-Command uv -ErrorAction SilentlyContinue)
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

# 定位系统 Python（用于兜底）
$systemPython = $null
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    try {
        $systemPython = (& py -3.12 -c "import sys; print(sys.executable)" 2>$null).Trim()
    } catch {}
}
if (-not $systemPython) {
    # 使用 PATH 中的 python 作为兜底
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        $systemPython = $pythonCmd.Source
    }
}
if (-not $systemPython) {
    # 使用当前用户的本地安装路径作为最终兜底
    $knownPython = Join-Path $env:LOCALAPPDATA "Programs\\Python\\Python312\\python.exe"
    if (Test-Path $knownPython) {
        $systemPython = $knownPython
    }
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
        & $uvExe venv --seed -p 3.12 .venv
    }
} else {
    Write-Host "  创建虚拟环境..." -ForegroundColor Yellow
    & $uvExe venv --seed -p 3.12 .venv
}

# 兜底修复 uv Python 缺失 _socket 的情况
$venvPython = ".\.venv\Scripts\python.exe"
$socketOk = $true
& $venvPython -c "import _socket" 2>$null
if ($LASTEXITCODE -ne 0) {
    $socketOk = $false
}
if (-not $socketOk -and $systemPython) {
    Write-Host "  检测到 uv Python 缺失 _socket，使用系统 Python 重建虚拟环境..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force .venv
    & $systemPython -m venv .venv
    $venvPython = ".\.venv\Scripts\python.exe"
}

# 激活虚拟环境
Write-Host ""
Write-Host "激活虚拟环境..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# 确保 pip 可用（uv 默认不安装 seed 包；旧环境可能缺 pip）
& $venvPython -m pip --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "检测到虚拟环境缺少 pip，正在安装..." -ForegroundColor Yellow
    & $venvPython -m ensurepip --upgrade
}

# 升级 pip (仅当虚拟环境创建后执行一次，或使用静默模式)
Write-Host ""
Write-Host "检查并升级 pip..." -ForegroundColor Yellow
& $venvPython -m pip install --upgrade pip --quiet
& $venvPython -m pip install -U setuptools wheel --quiet

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
& $venvPython -m pip install -e . --no-build-isolation

# 创建必要目录
Write-Host ""
Write-Host "创建必要目录..." -ForegroundColor Yellow
$folders = @(
    "cache",
    "cache/audio",
    "cache/hf",
    "tools",
    "tools/.data",
    "data",
    "config"
)
foreach ($f in $folders) {
    if (-not (Test-Path $f)) {
        New-Item -ItemType Directory $f | Out-Null
        Write-Host "  创建目录: $f" -ForegroundColor Green
    }
}

# 启用本地依赖隔离（方案1）
Write-Host ""
Write-Host "启用本地依赖隔离..." -ForegroundColor Yellow
$projectRoot = $PSScriptRoot
$cacheRoot = Join-Path $projectRoot "cache"
$hfCache = Join-Path $cacheRoot "hf"

$env:HF_HOME = $hfCache
$env:TRANSFORMERS_CACHE = $hfCache
$env:HUGGINGFACE_HUB_CACHE = Join-Path $hfCache "hub"
$env:XDG_CACHE_HOME = $cacheRoot

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
        $config = Get-Content "config/settings.json" -Encoding utf8 | ConvertFrom-Json
        $ocrLang = $config.ocr_lang
        $ocrBackend = $config.ocr_backend
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
Write-Host "检查并安装 Windows OCR 依赖..." -ForegroundColor Yellow

# 检查 Windows OCR 支持
Write-Host "  - Windows OCR (WinRT)..." -NoNewline
& $venvPython -c "import winrt.windows.media.ocr" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host " 已安装 (推荐)" -ForegroundColor Green
} else {
    Write-Host " 未安装" -ForegroundColor Yellow
    Write-Host "    正在安装 Windows OCR 依赖..." -ForegroundColor Yellow
    & $venvPython -m pip install winrt-Windows.Media.Ocr winrt-Windows.Globalization winrt-Windows.Storage.Streams winrt-Windows.Graphics.Imaging winrt-Windows.Foundation winrt-Windows.Foundation.Collections
    & $venvPython -c "import winrt.windows.media.ocr" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    Windows OCR 依赖安装完成" -ForegroundColor Green
    } else {
        Write-Host "    Windows OCR 安装失败，可稍后手动安装" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "检查并安装可选的 PaddleOCR-VL 依赖..." -ForegroundColor Yellow
Write-Host "  - PaddleOCR & PaddlePaddle..." -NoNewline
& $venvPython -c "import paddleocr" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host " 已安装" -ForegroundColor Green
} else {
    Write-Host " 未安装" -ForegroundColor Yellow
    $answer = Read-Host "    是否安装 PaddleOCR-VL 支持? (y/N)"
    if ($answer -eq "y" -or $answer -eq "Y") {
        Write-Host "    正在检查 GPU 设备..." -ForegroundColor Yellow
        $hasNvidia = $false
        if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
            $hasNvidia = $true
        }
        
        if ($hasNvidia) {
            Write-Host "    [检测到 NVIDIA GPU] 正在使用飞桨镜像源安装 GPU 版本的 paddlepaddle-gpu..." -ForegroundColor Green
            # 卸载 CPU 版以防冲突
            & $venvPython -m pip uninstall paddlepaddle -y --quiet 2>$null
            & $venvPython -m pip install paddlepaddle-gpu -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
        } else {
            Write-Host "    [未检测到 NVIDIA GPU] 正在安装 CPU 版本的 paddlepaddle..." -ForegroundColor Yellow
            & $venvPython -m pip uninstall paddlepaddle-gpu -y --quiet 2>$null
            & $venvPython -m pip install paddlepaddle
        }
        
        Write-Host "    正在安装 paddleocr 依赖..." -ForegroundColor Yellow
        & $venvPython -m pip install paddleocr>=3.4.0
        Write-Host "    正在安装 paddlex[ocr] 依赖..." -ForegroundColor Yellow
        & $venvPython -m pip install "paddlex[ocr]"
    }
}

Write-Host ""
Write-Host "检查第三方工具 (解包必需)..." -ForegroundColor Yellow

# 检查 FModelCLI
$fmodelCliPath = "tools/FModelCLI.exe"
Write-Host "  - FModelCLI.exe..." -NoNewline
if (Test-Path $fmodelCliPath) {
    Write-Host " 已找到" -ForegroundColor Green
} else {
    # 优先检查本地开发路径
    $devPaths = @(
        "E:/FModelCLI/dist/FModelCLI.exe",
        "E:/FModelCLI/FModelCLI/bin/Release/net8.0/win-x64/publish/FModelCLI.exe"
    )
    $copied = $false
    foreach ($path in $devPaths) {
        if (Test-Path $path) {
            New-Item -ItemType Directory -Force -Path "tools" | Out-Null
            Copy-Item $path $fmodelCliPath -Force
            $copied = $true
            break
        }
    }
    if ($copied -and (Test-Path $fmodelCliPath)) {
        Write-Host " 已从本地开发环境复制" -ForegroundColor Green
    } else {
        Write-Host " 未找到" -ForegroundColor Yellow
        $answer = Read-Host "    是否从 GitHub Releases 下载 FModelCLI.exe? (y/N)"
        if ($answer -eq "y" -or $answer -eq "Y") {
            try {
                $url = "https://github.com/Herselfta/FModelCLI/releases/latest/download/FModelCLI.exe"
                New-Item -ItemType Directory -Force -Path "tools" | Out-Null
                & curl.exe -L $url -o $fmodelCliPath
                if (Test-Path $fmodelCliPath) {
                    Write-Host "    下载完成: $fmodelCliPath" -ForegroundColor Green
                } else {
                    Write-Host "    下载失败，请手动下载: https://github.com/Herselfta/FModelCLI/releases/latest" -ForegroundColor Yellow
                    Write-Host "    下载 FModelCLI.exe 后放到: $fmodelCliPath" -ForegroundColor Yellow
                }
            } catch {
                Write-Host "    下载失败，请手动下载: https://github.com/Herselfta/FModelCLI/releases/latest" -ForegroundColor Yellow
                Write-Host "    下载 FModelCLI.exe 后放到: $fmodelCliPath" -ForegroundColor Yellow
            }
        } else {
            Write-Host "    已跳过下载 (可稍后在工具菜单触发或手动下载)" -ForegroundColor Gray
            Write-Host "    手动下载: https://github.com/Herselfta/FModelCLI/releases/latest" -ForegroundColor Gray
            Write-Host "    下载 FModelCLI.exe 后放到: $fmodelCliPath" -ForegroundColor Gray
        }
    }
}
Write-Host "    说明：FModelCLI 会自动下载 vgmstream 等依赖到 tools/.data/" -ForegroundColor Gray

# 完成
Write-Host ""
Write-Host "=== 环境配置完成! ===" -ForegroundColor Green
Write-Host ""
Write-Host "下一步:" -ForegroundColor Cyan
Write-Host "  1. 运行程序: .\run.ps1" -ForegroundColor White
Write-Host "  2. 或手动运行: .\.venv\Scripts\Activate.ps1 && python -m ludiglot" -ForegroundColor White
Write-Host ""
