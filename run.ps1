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

# 本地依赖隔离（缓存与工具路径）
$projectRoot = $PSScriptRoot
$cacheRoot = Join-Path $projectRoot "cache"
$hfCache = Join-Path $cacheRoot "hf"

$env:HF_HOME = $hfCache
$env:TRANSFORMERS_CACHE = $hfCache
$env:HUGGINGFACE_HUB_CACHE = Join-Path $hfCache "hub"
$env:XDG_CACHE_HOME = $cacheRoot
$env:FLAGS_enable_pir_api = "0"

# 检查安装状态
Write-Host "检查安装状态..." -ForegroundColor Yellow
& $venvPython -c "import ludiglot" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  警告: Ludiglot 未正确安装" -ForegroundColor Yellow
    Write-Host "  正在重新安装..." -ForegroundColor Yellow
    & $venvPython -m pip install -e . --quiet
}

# 检查 PaddleOCR-VL 后端状态并自动启动
if (Test-Path "config/settings.json") {
    try {
        $config = Get-Content "config/settings.json" -Encoding utf8 | ConvertFrom-Json
        if ($config.ocr_backend -eq "paddle_vl") {
            $url = $config.ocr_paddle_vl_url
            if ($url) {
                $uri = New-Object System.Uri($url)
                $hostName = $uri.Host
                if ($hostName -eq "localhost") { $hostName = "127.0.0.1" }
                $port = $uri.Port
                
                # 定义快速端口连接测试
                function Test-PortOpen {
                    param([string]$h, [int]$p)
                    $client = New-Object System.Net.Sockets.TcpClient
                    try {
                        $asyncResult = $client.BeginConnect($h, $p, $null, $null)
                        if ($asyncResult.AsyncWaitHandle.WaitOne(300)) {
                            $client.EndConnect($asyncResult) | Out-Null
                            return $true
                        }
                        return $false
                    } catch {
                        return $false
                    } finally {
                        $client.Close()
                    }
                }
                
                if (-not (Test-PortOpen $hostName $port)) {
                    Write-Host "检测到 PaddleOCR-VL 后端未启动，正在自动拉起本地 API 服务..." -ForegroundColor Yellow
                    # 在新窗口启动服务，方便用户查看加载进度和模型下载日志
                    Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass", "-NoExit", "-Command `& `'$venvPython`' tools/paddle_vl_server.py" -WindowStyle Minimized
                    
                    Write-Host "等待 PaddleOCR-VL 服务 (端口 $port) 响应..." -ForegroundColor Yellow
                    $retries = 45
                    $started = $false
                    while ($retries -gt 0) {
                        Start-Sleep -Seconds 1
                        if (Test-PortOpen $hostName $port) {
                            $started = $true
                            break
                        }
                        $retries--
                    }
                    if ($started) {
                        Write-Host "PaddleOCR-VL 服务已就绪！" -ForegroundColor Green
                    } else {
                        Write-Host "警告: 等待 PaddleOCR-VL 服务启动超时，将尝试继续启动 GUI..." -ForegroundColor Red
                    }
                } else {
                    Write-Host "检测到 PaddleOCR-VL 服务已在运行 (端口 $port)" -ForegroundColor Green
                }
            }
        }
    } catch {
        Write-Host "警告: 解析 settings.json 或检查 PaddleOCR-VL 后端失败: $_" -ForegroundColor Yellow
    }
}

# 启动程序
Write-Host ""
Write-Host "启动 Ludiglot GUI..." -ForegroundColor Green
Write-Host ""
& $venvPython -m ludiglot

