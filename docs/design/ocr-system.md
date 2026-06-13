# Windows OCR 集成说明

## 概述

Ludiglot 优先使用 **Windows 原生 OCR**（Windows.Media.Ocr）作为文本识别引擎，并提供与大语言模型（如 GLM-OCR）协同工作的多后端支持，致力于提供极速、低内存占用的识别体验。

## 优势

### 1. **性能优越**
- ⚡ **启动速度快**：无需加载大型深度学习模型，直接调用系统原生组件。
- ⚡ **识别速度快**：原生系统 API，响应迅速（< 0.05s）。
- 💾 **内存占用低**：仅约 50MB 内存占用，不需要 GPU。

### 2. **识别质量高**
- 📝 **英文识别准确**：特别针对游戏内常规排版文本进行了多尺度/Gamma 自适应预处理与空间融合。
- 🎯 **边界框精确**：准确定位字、词、句的视觉边界。
- 🔤 **字体兼容性好**：对非常规的游戏内定制字体也有出色的召回率。

### 3. **系统集成**
- 🔧 **无需额外配置**：依托 Windows 操作系统内置的 OCR 功能。
- 🌐 **多语言支持**：根据 Windows 系统的语言包设置自动匹配。

## OCR 后端

Ludiglot 目前支持以下 OCR 后端：

1. **Windows OCR (默认后端)** → 速度极快（<0.05s）、完全本地运行，内存占用低（约50MB），不需要复杂的深度学习环境。
2. **PaddleOCR-VL (原生 Python 后端)** → 运行 `tools/paddle_vl_server.py` 开启本地 API 服务。依赖飞桨 GPU/CPU 框架，较重且首次加载慢。
3. **PaddleOCR-VL (llama.cpp + GGUF 极速后端 - 推荐)** → 使用免安装的 `llama-server.exe` 运行 GGUF 格式的 `PaddleOCR-VL-1.6` 模型。免去庞大的 Paddle 依赖，加载速度 < 1s，显存占用暴降，识别响应提升至亚秒级。

## 安装与部署 (llama.cpp + GGUF 极速版)

### 1. 目录结构规范
将所有运行文件存放在 `tools/llama` 目录下以保持项目整洁：
```text
tools/llama/
├── llama-server.exe                    # 从 llama.cpp 官方 Windows-cuda 释放包解压的主程序
├── ggml.dll                            # 依赖的 ggml 库
├── cublas64_13.dll                     # CUDA 运行时依赖 dll
├── cublasLt64_13.dll                   # CUDA 运行时依赖 dll
├── cudart64_13.dll                     # CUDA 运行时依赖 dll
├── PaddleOCR-VL-1.6-GGUF.gguf          # 模型主文件 (来自 HuggingFace PaddlePaddle/PaddleOCR-VL-1.6-GGUF)
└── PaddleOCR-VL-1.6-GGUF-mmproj.gguf   # 多模态投影器文件
```

### 2. 启动服务命令
在 PowerShell 中进入 `tools/llama` 目录运行以下命令开启服务：
```powershell
.\llama-server.exe -m PaddleOCR-VL-1.6-GGUF.gguf --mmproj PaddleOCR-VL-1.6-GGUF-mmproj.gguf --port 8000 --ctx-size 2048 -ngl 99
```
* `-ngl 99` 指示将所有网络层卸载至 GPU 进行极速硬件加速。

### 3. 系统配置
在 `config/settings.json` 中配置 `"ocr_backend": "paddle_vl"`，并确保 `"ocr_paddle_vl_url"` 为 `"http://localhost:8000/v1"` 即可无缝对接。

## 原生飞桨后端安装要求 (若不使用 GGUF)

### 核心依赖（自动安装）

```bash
pip install winrt-Windows.Media.Ocr
pip install winrt-Windows.Globalization
pip install winrt-Windows.Storage.Streams
pip install winrt-Windows.Graphics.Imaging
pip install winrt-Windows.Foundation
pip install winrt-Windows.Foundation.Collections
```

### 可选依赖 (PaddleOCR-VL)

#### GPU 版本 (推荐，支持 CUDA 12.x)

```bash
# 卸载 CPU 版本防止冲突
pip uninstall paddlepaddle -y
# 使用飞桨镜像源安装 GPU 版本
pip install paddlepaddle-gpu -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
# 安装其他依赖
pip install paddleocr>=3.4.0 "paddlex[ocr]"
```

#### CPU 版本 (推理缓慢，仅作备用)

```bash
pip install paddlepaddle paddleocr>=3.4.0 "paddlex[ocr]"
```

### 系统要求

- **操作系统**：Windows 10 (1809+) 或 Windows 11
- **语言包**：需要在 Windows 设置中安装对应语言的 OCR 功能包（仅在使用 Windows OCR 时需要）。

#### 安装 Windows OCR 语言包

1. 打开 **设置** → **时间和语言** → **语言**
2. 点击 "添加语言"
3. 选择 **English (United States)** 或其他目标语言
4. 确保勾选 "**光学字符识别 (OCR)**" 并安装。

## 配置选项

在 `config/settings.json` 中配置：

```json
{
  "ocr_lang": "en",           // OCR 语言（en/zh等）
  "ocr_backend": "paddle_vl",  // 后端选择：auto/windows/paddle_vl
  "ocr_paddle_vl_url": "http://localhost:8000/v1", // PaddleOCR-VL API 端口
  "ocr_paddle_vl_model": "PaddlePaddle/PaddleOCR-VL" // 大模型名称
}
```

## 性能对比

基于测试图片 (500x80, 纯英文文本)：

| 后端 | 启动时间 | 识别时间 | 内存占用 | 准确率 |
|------|----------|----------|----------|--------|
| **Windows OCR** | < 0.1s | ~0.05s | ~50 MB | 95%+ |

## 故障排除

### 问题 1：Windows OCR 无法识别任何文本

**可能原因**：
- 系统未安装对应语言的 OCR 包。

**解决方案**：
1. 检查 Windows 设置中是否安装了英语 OCR 包。
2. 确认截图区域不是黑色或全白（可能属于保护性内容）。

---

**文档版本**: 1.1  
**最后更新**: 2026-06-13
