$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$env:FLAGS_enable_pir_api = "0"
$env:FLAGS_use_pir_api = "0"
$env:FLAGS_enable_pir_in_executor = "0"
$env:FLAGS_use_pir = "0"
$env:FLAGS_enable_new_ir = "0"
$env:FLAGS_use_new_executor = "0"
$env:FLAGS_use_mkldnn = "0"
$env:FLAGS_use_onednn = "0"
$env:PADDLE_ENABLE_PIR = "0"

$tesseractCandidates = @()
$tesseractCmd = Get-Command tesseract -ErrorAction SilentlyContinue
if ($tesseractCmd) {
  $tesseractCandidates += $tesseractCmd.Source
}
$tesseractCandidates += @(
  (Join-Path $env:ProgramFiles "Tesseract-OCR\tesseract.exe"),
  (Join-Path ${env:ProgramFiles(x86)} "Tesseract-OCR\tesseract.exe")
) | Where-Object { $_ -and (Test-Path $_) }

if (-not $tesseractCandidates) {
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget install --id UB-Mannheim.TesseractOCR -e --silent --accept-source-agreements --accept-package-agreements | Out-Null
    $tesseractCandidates += @(
      (Join-Path $env:ProgramFiles "Tesseract-OCR\tesseract.exe"),
      (Join-Path ${env:ProgramFiles(x86)} "Tesseract-OCR\tesseract.exe")
    ) | Where-Object { $_ -and (Test-Path $_) }
  }
}

if ($tesseractCandidates) {
  $tesseractDir = Split-Path -Parent $tesseractCandidates[0]
  if ($env:PATH -notlike "*$tesseractDir*") {
    $env:PATH = "$tesseractDir;$env:PATH"
  }
}

$venv = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venv)) {
  python -m venv .venv
}

& $venv -m pip install -e .
& $venv -m ludiglot gui --config "config/settings.json"
