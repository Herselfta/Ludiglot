<div align="center">

# 🌐 Ludiglot

**智能游戏文本翻译助手 | 实时 OCR + 语音播放**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows)](https://www.microsoft.com/windows)
[![OCR: Windows](https://img.shields.io/badge/OCR-Windows%20Native-00A4EF)](PrivateDevDoc/WindowsOCR.md)

[English](README_EN.md) | 简体中文

</div>

---

## ✨ 特性一览

### 🚀 核心功能

- **🔍 智能 OCR**：Windows 原生 OCR（启动 < 0.1s，识别 ~0.05s）自动回退 PaddleOCR/Tesseract
- **🎯 混合内容识别**：智能区分单行标题与多行长文本，精准匹配
- **🌏 即时翻译**：覆盖层浮窗显示中文翻译，支持标题高亮
- **🎵 语音播放**：自动播放角色语音（支持 Hash/Event 双重匹配）
- **⌨️ 全局热键**：`Alt+W` 快速截图识别，`Alt+Q` 切换浮窗

### ⚡ 性能优势

| 特性 | Windows OCR | PaddleOCR | 提升 |
|------|-------------|-----------|------|
| **启动时间** | < 0.1s | ~0.6s | **6x faster** |
| **识别速度** | ~0.05s | ~0.3s | **6x faster** |
| **内存占用** | ~50 MB | ~500 MB | **90% less** |
| **英文准确率** | 95%+ | 93%+ | **更高** |

详细说明请查看 [WindowsOCR.md](PrivateDevDoc/WindowsOCR.md)

---

## 📦 快速开始

> **💡 温馨提示**：本程序核心依赖一个 `game_text_db.json` 数据库。
> - 如果你是开发者或需要最新数据，请完成 **步骤 2**。
> - 如果你已有他人分享的 `game_text_db.json`，可以跳过步骤 2，直接将文件放入 `data` 目录，并在配置中关闭自动更新。

### 方式一：一键运行（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/yourusername/Ludiglot.git
cd Ludiglot

# 2. 准备数据（必需）
# 方法 A (推荐)：克隆 WutheringData
git clone https://github.com/Dimbreath/WutheringData.git data/WutheringData
# 或者手动将 WutheringData 放到 data 目录下

# 3. 下载第三方工具（可选，用于音频功能）
# FModel.exe (GPL-3.0): 从 https://fmodel.app/ 下载，放到 tools/ 目录
# vgmstream: 从 https://github.com/vgmstream/vgmstream 下载，解压到 tools/vgmstream/
# 详见 tools/README.md

# 4. 配置文件
copy config\settings.example.json config\settings.json
# 然后根据需要编辑 settings.json 中的路径

# 5. 一键配置环境 (Windows)
.\setup.ps1
# 或
setup.bat          # CMD

# 6. 一键启动程序
.\run.ps1          # PowerShell
# 或
run.bat            # CMD
```

### 方式二：手动安装

<details>
<summary>点击展开详细步骤</summary>

#### 1. 环境要求

- **Python**: 3.10+ ([下载地址](https://www.python.org/downloads/))
- **操作系统**: Windows 10/11（推荐）
- **可选**: GPU（CUDA）用于 PaddleOCR 加速

#### 2. 创建虚拟环境

**Windows (PowerShell):**
```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass  # 如需要
.\.venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### 3. 安装依赖

```bash
# 升级 pip
python -m pip install --upgrade pip

# 安装项目（开发模式）
pip install -e .
```

#### 4. 可选：安装增强 OCR

**Windows OCR（推荐）:**
```bash
pip install winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging winrt-Windows.Storage.Streams
```

**PaddleOCR（GPU 加速）:**
```bash
# CPU 版本
pip install paddlepaddle paddleocr

# GPU 版本（CUDA 11.2+）
pip install paddlepaddle-gpu paddleocr
```

</details>---

## 🎮 使用指南

### 1. 配置文件

复制配置模板并修改：

```bash
copy config\settings.example.json config\settings.json
```

主要配置项：

```json
{
  "multitext_en": "path/to/MultiText_EN.json",
  "multitext_zh": "path/to/MultiText_ZH.json",
  "capture_mode": "window",              // image/window/region
  "window_title": "YourGameWindow",      // 窗口标题（window 模式）
  "capture_region": [0, 0, 1920, 1080],  // 截图区域（region 模式）
  "hotkey_capture": "alt+w",             // OCR 截图热键
  "hotkey_toggle": "alt+q",              // 切换浮窗
  "audio_cache_path": "audio_cache/",    // 语音缓存目录
  "ocr_mode": "auto"                     // auto/windows/paddle/tesseract
}
```

### 2. 启动 GUI

```bash
# 使用默认配置
python -m ludiglot

# 指定配置文件
python -m ludiglot gui --config config/settings.json
```

**Tray 菜单功能**：

- **Update Database**：自动从 GitHub 拉取最新 WutheringData 并重建数据库（需要 Git 已安装）
- **Font Size**：调整浮窗字体大小（8-24pt，默认 13pt）
- **Show/Hide**：快速显示/隐藏翻译浮窗
- **Quit**：退出程序

右键点击系统托盘图标可以快速访问这些功能。

### 3. CLI 命令

#### 构建文本数据库

```bash
python -m ludiglot build \
  --en MultiText_EN.json \
  --zh MultiText_ZH.json \
  --output game_text_db.json
```

#### OCR 识别截图

```bash
python -m ludiglot ocr \
  --image screenshot.png \
  --db game_text_db.json \
  --lang en
```

#### 音频提取与转换

```bash
# 从 FModel 导出的 .wem 文件转换
python -m ludiglot audio-extract \
  --wem-root /path/to/FModel/Export \
  --cache audio_cache/

# 自动化构建并测试
python -m ludiglot audio-build \
  --test-text-key Main_Character_1_1_1
```

---

## 📁 项目结构

```
Ludiglot/
├── src/ludiglot/
│   ├── core/              # 核心模块
│   │   ├── ocr.py         # OCR 引擎（Windows/Paddle/Tesseract）
│   │   ├── lookup.py      # 文本检索与匹配
│   │   └── smart_match.py # 智能混合内容匹配
│   ├── adapters/          # 游戏适配器
│   │   └── wuthering/     # 鸣潮适配器
│   └── ui/                # GUI 界面
│       └── overlay_window.py  # 浮窗主窗口
├── config/                # 配置文件
│   └── settings.example.json
├── tools/                 # 辅助工具
│   ├── FModel.exe         # 游戏资源提取
│   ├── vgmstream/         # 音频转换
│   └── wwiser.pyz         # BNK → TXTP
├── setup.ps1              # 一键配置脚本
├── run.ps1                # 一键运行脚本
└── README.md
```

---

## 🔧 高级功能

### 智能混合内容识别

系统能自动识别 OCR 结果中的不同内容类型：

- **单行标题**：短文本（≤ 3 词，无标点）→ 优先显示为标题
- **多行长文本**：描述性内容 → 匹配完整文本
- **混合内容**：标题 + 描述 → 分别匹配，标题高亮显示

示例：
```
OCR 识别: "Ms. Voss\nLong descriptive text here..."
显示结果: 【Ms. Voss】
          
          [对应的中文翻译]
```

### 语音自动播放

支持两种匹配方式：

1. **Hash 匹配**：直接匹配 `audio_hash`（最快）
2. **Event 匹配**：通过 `audio_event` 查找 BNK → TXTP → 转码播放

配置说明：
```json
{
  "audio_wem_root": "FModel导出的WEM目录",
  "audio_bnk_root": "FModel导出的BNK目录",
  "vgmstream_path": "vgmstream-cli.exe路径",
  "wwiser_path": "wwiser.pyz路径"
}
```

---

## 🤝 贡献指南

欢迎贡献！详见 [CONTRIBUTING.md](CONTRIBUTING.md)

### 快速指南

1. Fork 本仓库
2. 创建特性分支: `git checkout -b feature/AmazingFeature`
3. 提交更改: `git commit -m 'Add AmazingFeature'`
4. 推送分支: `git push origin feature/AmazingFeature`
5. 提交 Pull Request

---

## 📜 许可证

本项目采用 [MIT License](LICENSE) 许可。

---

## 🙏 致谢

- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - GUI 框架
- [Windows.Media.Ocr](https://docs.microsoft.com/en-us/uwp/api/windows.media.ocr) - Windows OCR
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) - 备选 OCR 引擎
- [vgmstream](https://github.com/vgmstream/vgmstream) - 游戏音频解码
- [FModel](https://fmodel.app/) - 游戏资源提取
- [WutheringData](https://github.com/Dimbreath/WutheringData) - 鸣潮游戏文本与音频数据库

---

<div align="center">

**⭐ 如果觉得项目有用，请给个 Star 支持！**

Made with ❤️ by the Ludiglot Community

</div>
