# Windows OCR 集成说明

## 概述

Ludiglot 现在优先使用 **Windows 原生 OCR**（Windows.Media.Ocr）作为文本识别引擎，提供更快、更准确的识别体验。

## 优势

### 1. **性能优越**
- ⚡ **启动速度快**：无需加载大型深度学习模型
- ⚡ **识别速度快**：原生系统调用，响应迅速
- 💾 **内存占用低**：不需要 GPU 或大量 RAM

### 2. **识别质量高**
- 📝 **英文识别准确**：对游戏界面文本识别率高
- 🎯 **边界框精确**：准确定位文本位置
- 🔤 **字体兼容性好**：支持多种字体样式

### 3. **系统集成**
- 🔧 **无需额外配置**：使用 Windows 系统内置能力
- 🌐 **多语言支持**：根据系统语言包自动适配
- 🔒 **稳定可靠**：由 Microsoft 官方维护

## OCR 后端优先级

Ludiglot 使用以下后端优先级策略（`ocr_backend: "auto"` 模式）：

```
1. Windows OCR (优先) → 速度快、质量高
2. PaddleOCR (备选)   → 深度学习模型，支持更多场景
3. Tesseract (兜底)   → 开源方案，最大兼容性
```

如果指定 `ocr_backend: "glm"`，将优先调用 **GLM-OCR (本地 Transformers)**，失败后回退到 Windows/Paddle/Tesseract。


### 自动回退机制

- 如果 Windows OCR 不可用（依赖缺失或无语言包）→ 自动使用 PaddleOCR
- 如果 PaddleOCR 识别质量差（置信度 < 0.6）→ 尝试 Tesseract 兜底
- 所有后端失败 → 返回空结果

## 安装要求

### 核心依赖（自动安装）

```bash
pip install winrt-Windows.Media.Ocr
pip install winrt-Windows.Globalization
pip install winrt-Windows.Storage.Streams
pip install winrt-Windows.Graphics.Imaging
pip install winrt-Windows.Foundation
pip install winrt-Windows.Foundation.Collections
```

或者使用项目的可编辑安装：

```bash
pip install -e .
```


### 系统要求

- **操作系统**：Windows 10 (1809+) 或 Windows 11
- **语言包**：需要在 Windows 设置中安装对应语言的 OCR 包

#### 安装 Windows OCR 语言包

1. 打开 **设置** → **时间和语言** → **语言**
2. 点击"添加语言"
3. 选择 **English (United States)** 或其他目标语言
4. 确保勾选 "**语言功能**" → "**光学字符识别 (OCR)**"
5. 下载并安装

> 💡 **提示**：如果未安装语言包，Ludiglot 会自动回退到 PaddleOCR/Tesseract，并在日志中提示安装方法。

## 配置选项

在 `config/settings.json` 中：

```json
{
  "ocr_lang": "en",           // OCR 语言（en/zh/ja等）
  "ocr_mode": "auto",         // OCR 模式：auto/gpu/cpu
  "ocr_backend": "glm",       // 后端选择：auto/paddle/tesseract/glm/glm_ollama
  "ocr_glm_model": "zai-org/GLM-OCR",
  "ocr_glm_timeout": 30,
  "ocr_glm_endpoint": "http://127.0.0.1:11434"
}
```

### OCR Backend 选项

- `"auto"` (推荐)：Windows OCR → PaddleOCR → Tesseract
- `"paddle"`：仅使用 PaddleOCR（需要 GPU 或 CPU 推理）
- `"tesseract"`：仅使用 Tesseract（开源方案）
- `"glm"`：使用 GLM-OCR（本地 Transformers），失败自动回退
- `"glm_ollama"`：使用 GLM-OCR（Ollama 服务），失败自动回退

### GLM-OCR (本地 Transformers) 快速启用

1. 配置 `ocr_backend: "glm"`
2. 若未安装依赖，程序会自动尝试安装 `ludiglot[glm]`
3. 首次运行会自动下载 `zai-org/GLM-OCR` 模型

### GLM-OCR (Ollama) 快速启用

1. 安装 Ollama
2. 拉取模型：`ollama pull glm-ocr`
3. 确保服务可访问（默认 `http://127.0.0.1:11434`）
4. 配置 `ocr_backend: "glm_ollama"`

## 日志示例

成功使用 Windows OCR 时的日志输出：

```
[OCR] 尝试后端: Windows OCR (优先)
[OCR] Windows OCR 初始化成功 (语言: en)
[OCR] Windows OCR 成功识别 3 行文本
[OCR] 实际使用后端: windows
```

依赖缺失时的日志输出：

```
[OCR] 尝试后端: Windows OCR (优先)
[OCR] Windows OCR 不可用：WinRT 依赖缺失 (ModuleNotFoundError)
[OCR] 提示：可通过 'pip install winrt-Windows.Media.Ocr ...' 安装
[OCR] 尝试后端: PaddleOCR
```

语言包未安装时的日志输出：

```
[OCR] Windows OCR 不可用：系统未安装任何 OCR 语言包
[OCR] 提示：请在 Windows 设置 -> 时间和语言 -> 语言中添加语言包
```

## 性能对比

基于测试图片 (500x80, 纯英文文本)：

| 后端 | 启动时间 | 识别时间 | 内存占用 | 准确率 |
|------|----------|----------|----------|--------|
| **Windows OCR** | < 0.1s | ~0.05s | ~50 MB | 95%+ |
| PaddleOCR (CPU) | ~2s | ~0.3s | ~500 MB | 90%+ |
| Tesseract | ~0.5s | ~0.2s | ~100 MB | 85%+ |
| **GLM-OCR (CUDA)** | ~10s | ~0.72s | ~2GB | 98%+ |

> 📊 **结论**：Windows OCR 在速度和内存占用上具有显著优势，尤其适合实时游戏场景。GLM-OCR 提供最高的识别准确率，适合对质量要求高的场景。

## GLM-OCR 性能优化

GLM-OCR 使用 Transformers 框架运行本地 VLM 模型进行 OCR。通过以下优化，在 RTX 3080 上可实现约 0.72s 的单帧识别时间：

### 优化策略

1. **torch.compile 编译优化** (默认启用)
   - 使用 `reduce-overhead` 模式减少 Python 调用开销
   - 利用 CUDA Graphs 进行运算图缓存
   - 环境变量控制：`LUDIGLOT_GLM_COMPILE=0` 可禁用

2. **Triton 加速** (Windows)
   - 需要安装兼容版本的 triton-windows
   - 安装命令：`pip install triton-windows==3.1.0.post17`
   - setup.ps1 会自动安装

3. **Token 数量优化**
   - 默认 `max_new_tokens=48`，足够识别典型游戏字幕
   - 可通过 `LUDIGLOT_GLM_OCR_MAX_TOKENS` 环境变量调整
   - 减少 token 数量可显著提升速度

4. **SDPA 注意力机制**
   - 模型自动使用 Scaled Dot-Product Attention
   - 在支持的 GPU 上自动启用 Flash Attention

### 环境变量配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `LUDIGLOT_GLM_COMPILE` | `1` | 是否启用 torch.compile |
| `LUDIGLOT_GLM_COMPILE_MODE` | `reduce-overhead` | 编译模式 |
| `LUDIGLOT_GLM_OCR_MAX_TOKENS` | `48` | 最大生成 token 数 |
| `LUDIGLOT_GLM_MAX_IMAGE_SIZE` | `1024` | 最大图像尺寸 |

### 性能调优建议

- **首次运行较慢**：torch.compile 需要编译内核，首次推理会慢约 50%
- **稳定性能**：连续运行后性能会稳定在 ~0.72s
- **长文本**：如需识别更长文本，可增加 `max_new_tokens` 到 64-128

## 故障排除

### 问题 1：Windows OCR 无法识别任何文本

**可能原因**：
- 系统未安装对应语言的 OCR 包
- 图片格式不支持（需要 PNG/JPG/BMP）

**解决方案**：
1. 检查 Windows 设置中是否安装了英语 OCR 包
2. 确认图片格式正确
3. 查看日志中的详细错误信息

### 问题 2：WinRT 模块导入失败

**错误信息**：
```
ModuleNotFoundError: No module named 'winrt.windows.media.ocr'
```

**解决方案**：
```bash
pip install winrt-Windows.Media.Ocr winrt-Windows.Globalization winrt-Windows.Storage.Streams winrt-Windows.Graphics.Imaging winrt-Windows.Foundation winrt-Windows.Foundation.Collections
```

### 问题 3：识别质量不如预期

**可能原因**：
- 图片分辨率过低
- 文本字体过于特殊
- 背景干扰严重

**解决方案**：
- 确保截图清晰（建议至少 720p）
- 使用 `prefer_tesseract=True` 参数尝试其他后端
- 检查 `ocr_backend` 配置，尝试 PaddleOCR

## 开发者参考

### API 使用示例

```python
from ludiglot.core.ocr import OCREngine, group_ocr_lines
from pathlib import Path

# 初始化引擎（默认使用 Windows OCR 优先）
engine = OCREngine(lang='en', mode='auto')

# 识别图片
image_path = Path('screenshot.png')
box_lines = engine.recognize_with_boxes(image_path)
lines = group_ocr_lines(box_lines)

# 检查使用的后端
backend = engine.last_backend
print(f"使用后端: {backend}")  # 输出: windows / paddle / tesseract

# 打印结果
for text, confidence in lines:
    print(f"{text} (置信度={confidence:.3f})")
```

### 强制使用特定后端

```python
# 仅使用 Windows OCR
lines = engine.recognize_with_boxes(image_path, prefer_tesseract=False)

# 强制使用 Tesseract
lines = engine.recognize_with_boxes(image_path, prefer_tesseract=True)
```

## 更新日志

### v0.0.1 (2026-01-21)

- ✅ 实现 Windows 原生 OCR 集成
- ✅ 优先级策略：Windows OCR → PaddleOCR → Tesseract
- ✅ 自动回退机制和详细日志
- ✅ 完整的依赖管理和错误提示
- ✅ 修复边界框解析问题（从 words 聚合）
- ✅ 综合测试验证多种场景

## 贡献

如遇到 Windows OCR 相关问题，请提供：
1. 系统版本（Windows 10/11）
2. 已安装的语言包列表
3. 完整的错误日志
4. 测试图片（如可能）

---

**文档版本**: 1.0  
**最后更新**: 2026-01-21
