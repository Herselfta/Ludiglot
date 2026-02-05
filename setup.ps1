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

# 定位系统 Python（用于兜底）
$systemPython = $null
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    try {
        $systemPython = (& py -3.12 -c "import sys; print(sys.executable)" 2>$null).Trim()
    } catch {}
}
if (-not $systemPython) {
    $knownPython = "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python312\\python.exe"
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
        & $uvExe venv -p 3.12 .venv
    }
} else {
    Write-Host "  创建虚拟环境..." -ForegroundColor Yellow
    & $uvExe venv -p 3.12 .venv
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
    "cache/paddlex",
    "tools",
    "tools/.data",
    "tools/tesseract",
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
$paddlexCache = Join-Path $cacheRoot "paddlex"
$tesseractDir = Join-Path $projectRoot "tools\\tesseract"
$tesseractExe = Join-Path $tesseractDir "tesseract.exe"

$env:HF_HOME = $hfCache
$env:TRANSFORMERS_CACHE = $hfCache
$env:HUGGINGFACE_HUB_CACHE = Join-Path $hfCache "hub"
$env:XDG_CACHE_HOME = $cacheRoot
$env:PADDLE_PDX_CACHE_HOME = $paddlexCache

if (Test-Path $tesseractExe) {
    $env:TESSERACT_CMD = $tesseractExe
    $env:PATH = "$tesseractDir;$env:PATH"
}

# 尝试将 ~/.paddlex 指向项目缓存（仅在不存在时创建）
$paddlexHome = Join-Path $env:USERPROFILE ".paddlex"
if (-not (Test-Path $paddlexHome)) {
    try {
        & cmd /c "mklink /J `"$paddlexHome`" `"$paddlexCache`"" | Out-Null
        Write-Host "  已创建 .paddlex 目录联接 -> cache/paddlex" -ForegroundColor Green
    } catch {
        Write-Host "  无法创建 .paddlex 联接，将仅使用环境变量" -ForegroundColor Yellow
    }
} else {
    try {
        $attr = (Get-Item $paddlexHome).Attributes
        if (($attr -band [IO.FileAttributes]::ReparsePoint) -eq 0) {
            Write-Host "  检测到现有 .paddlex 目录，未覆盖（避免破坏用户数据）" -ForegroundColor Gray
        }
    } catch {
        Write-Host "  检测 .paddlex 状态失败，已跳过" -ForegroundColor Gray
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
Write-Host "选择 OCR 后端 (可多选，首个为首选)..." -ForegroundColor Yellow
Write-Host "  1. Paddle-OCR" -ForegroundColor White
Write-Host "  2. Windows-OCR" -ForegroundColor White
Write-Host "  3. Tesseract-OCR" -ForegroundColor White
Write-Host "  提示: GLM-OCR 通过 Ollama 使用，无需额外安装" -ForegroundColor Gray
$choiceRaw = Read-Host "  请输入数字 (例: 1 2 3)"

$selected = @()
if ($choiceRaw) {
    $matches = [regex]::Matches($choiceRaw, "[1-3]")
    foreach ($m in $matches) {
        $n = [int]$m.Value
        if (-not ($selected -contains $n)) {
            $selected += $n
        }
    }
}
if ($selected.Count -eq 0) {
    Write-Host "  未识别有效选择，跳过 OCR 后端安装" -ForegroundColor Gray
}

$selectPaddle = $false
$selectWindows = $false
$selectTesseract = $false

foreach ($n in $selected) {
    switch ($n) {
        1 { $selectPaddle = $true }
        2 { $selectWindows = $true }
        3 { $selectTesseract = $true }
    }
}

$preferredBackend = $null
if ($selected.Count -gt 0) {
    switch ($selected[0]) {
        1 { $preferredBackend = "paddle" }
        2 { $preferredBackend = "windows" }
        3 { $preferredBackend = "tesseract" }
    }
}

if ($preferredBackend -and (Test-Path "config/settings.json")) {
    try {
        $configLines = Get-Content "config/settings.json" -Encoding utf8
        $updated = $configLines -replace '"ocr_backend"\s*:\s*"[^"]+"', ('"ocr_backend": "' + $preferredBackend + '"')
        if ($updated -ne $configLines) {
            Set-Content -Path "config/settings.json" -Encoding utf8 -Value $updated
            Write-Host "  已设置首选 OCR 后端: $preferredBackend" -ForegroundColor Green
        }
    } catch {
        Write-Host "  设置首选 OCR 后端失败，可稍后手动修改 config/settings.json" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "检查并安装选择的 OCR 后端..." -ForegroundColor Yellow

# 检查 Windows OCR 支持
Write-Host "  - Windows OCR (WinRT)..." -NoNewline
& $venvPython -c "import winrt.windows.media.ocr" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host " 已安装 (推荐)" -ForegroundColor Green
} else {
    Write-Host " 未安装" -ForegroundColor Yellow
    if ($selectWindows) {
        Write-Host "    正在安装 Windows OCR 依赖..." -ForegroundColor Yellow
        & $venvPython -m pip install winrt-Windows.Media.Ocr winrt-Windows.Globalization winrt-Windows.Storage.Streams winrt-Windows.Graphics.Imaging winrt-Windows.Foundation winrt-Windows.Foundation.Collections
        & $venvPython -c "import winrt.windows.media.ocr" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    Windows OCR 依赖安装完成" -ForegroundColor Green
        } else {
            Write-Host "    Windows OCR 安装失败，可稍后手动安装" -ForegroundColor Yellow
        }
    } else {
        Write-Host "    如果您使用的是 Windows 10/11，强烈建议安装: pip install winrt-Windows.Media.Ocr" -ForegroundColor Gray
    }
}

# 检查 PaddleOCR 支持
Write-Host "  - PaddleOCR..." -NoNewline
& $venvPython -c "import paddleocr" 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host " 已安装" -ForegroundColor Green
    $paddleAvailable = $true
} else {
    Write-Host " 未安装 (可选)" -ForegroundColor Cyan
    Write-Host "    如需更高识别率且不介意性能，可安装: pip install ludiglot[paddle]" -ForegroundColor Gray
    $paddleAvailable = $false
    if ($selectPaddle) {
        Write-Host "    正在安装 PaddleOCR 依赖..." -ForegroundColor Yellow
        & $venvPython -m pip install -e .[paddle]
        & $venvPython -c "import paddleocr" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    PaddleOCR 依赖安装完成" -ForegroundColor Green
            $paddleAvailable = $true
        } else {
            Write-Host "    PaddleOCR 安装失败，可稍后手动安装" -ForegroundColor Yellow
        }
    }
}

Write-Host "  - Tesseract OCR..." -NoNewline
$tesseractOk = $false
$tesseractLocalExe = Join-Path $PSScriptRoot "tools\\tesseract\\tesseract.exe"
if (Test-Path $tesseractLocalExe) {
    $tesseractOk = $true
    $env:TESSERACT_CMD = $tesseractLocalExe
    $env:PATH = (Split-Path $tesseractLocalExe) + ";" + $env:PATH
} else {
    try {
        $tessCmd = Get-Command tesseract -ErrorAction SilentlyContinue
        if ($tessCmd) { $tesseractOk = $true }
    } catch {}
}
if ($tesseractOk) {
    Write-Host " 已安装" -ForegroundColor Green
} else {
    Write-Host " 未安装 (可选)" -ForegroundColor Cyan
    if ($selectTesseract) {
        $wingetCmd = Get-Command winget -ErrorAction SilentlyContinue
        if ($wingetCmd) {
            Write-Host "    正在安装 Tesseract (优先本地目录)..." -ForegroundColor Yellow
            $tessLocation = Join-Path $PSScriptRoot "tools\\tesseract"
            winget install --id UB-Mannheim.TesseractOCR -e --accept-package-agreements --accept-source-agreements --location $tessLocation
            if (Test-Path $tesseractLocalExe) {
                Write-Host "    Tesseract 已安装到 tools/tesseract" -ForegroundColor Green
                $env:TESSERACT_CMD = $tesseractLocalExe
                $env:PATH = (Split-Path $tesseractLocalExe) + ";" + $env:PATH
            } else {
                $tessCmd = Get-Command tesseract -ErrorAction SilentlyContinue
                if ($tessCmd) {
                    Write-Host "    Tesseract 已安装到系统 (非项目目录)" -ForegroundColor Yellow
                } else {
                    Write-Host "    Tesseract 安装失败，可稍后手动安装" -ForegroundColor Yellow
                }
            }
        } else {
            Write-Host "    未找到 winget，请手动安装 Tesseract (UB-Mannheim 版本)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "    需要系统安装 Tesseract 可执行文件" -ForegroundColor Gray
    }
}

# 预下载 PaddleOCR 模型（可选）
if ($paddleAvailable -and $selectPaddle) {
    Write-Host "    预下载 PaddleOCR 模型..." -ForegroundColor Yellow
    $lang = "en"
    if ($ocrLang) {
        if ($ocrLang -like "zh*") { $lang = "ch" }
        elseif ($ocrLang -like "en*") { $lang = "en" }
    }
    @"
from paddleocr import PaddleOCR
PaddleOCR(lang='$lang')
print('PaddleOCR model ready')
"@ | & $venvPython
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    预下载失败，可稍后手动触发" -ForegroundColor Yellow
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
        Write-Host "    为了安全起见，需要手动下载 FModelCLI.exe" -ForegroundColor Cyan
        Write-Host "    请访问: https://github.com/Herselfta/FModelCLI/releases" -ForegroundColor Cyan
        Write-Host "    下载最新版本的 FModelCLI.exe 到 tools/ 目录" -ForegroundColor Cyan
        Write-Host "    验证文件签名/校验和后再使用" -ForegroundColor Cyan
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
