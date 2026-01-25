@echo off
setlocal
set ROOT=%~dp0
cd /d %ROOT%
set FLAGS_enable_pir_api=0
set FLAGS_use_pir_api=0
set FLAGS_enable_pir_in_executor=0
set FLAGS_use_pir=0
set FLAGS_enable_new_ir=0
set FLAGS_use_new_executor=0
set FLAGS_use_mkldnn=0
set FLAGS_use_onednn=0
set PADDLE_ENABLE_PIR=0
set TESSERACT_DEFAULT=%ProgramFiles%\Tesseract-OCR\tesseract.exe
set TESSERACT_DEFAULT_X86=%ProgramFiles(x86)%\Tesseract-OCR\tesseract.exe
if exist "%TESSERACT_DEFAULT%" set PATH=%ProgramFiles%\Tesseract-OCR;%PATH%
if exist "%TESSERACT_DEFAULT_X86%" set PATH=%ProgramFiles(x86)%\Tesseract-OCR;%PATH%

where tesseract >nul 2>nul
if errorlevel 1 (
  where winget >nul 2>nul
  if not errorlevel 1 (
    winget install --id UB-Mannheim.TesseractOCR -e --silent --accept-source-agreements --accept-package-agreements >nul 2>nul
    if exist "%TESSERACT_DEFAULT%" set PATH=%ProgramFiles%\Tesseract-OCR;%PATH%
    if exist "%TESSERACT_DEFAULT_X86%" set PATH=%ProgramFiles(x86)%\Tesseract-OCR;%PATH%
  )
)
if not exist .venv\Scripts\python.exe (
  python -m venv .venv
)
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m ludiglot gui --config "config\settings.json"
endlocal
