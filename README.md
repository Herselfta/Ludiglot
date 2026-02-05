<div align="center">

# 🌐 Ludiglot

**智能游戏文本翻译助手 | 实时 OCR + 语音播放**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows)](https://www.microsoft.com/windows)

[English](docs/en/README.md) | 简体中文

</div>

---

## ✨ 特性一览

- **🔍 智能 OCR**：Windows 原生 OCR 优先，秒级启动。支持 GLM-OCR (本地 Transformers) 一体化部署，智能回退 PaddleOCR/Tesseract。
- **🌏 即时翻译**：非侵入式复刻《鸣潮》风格覆盖层，实时检索官方文本。
- **🎵 原声语音**：自动定位并播放对应官方语音，支持 Wwise 逻辑推导。
- **⌨️ 全局集成**：热键截图、历史记录、智能标题分离一应俱全。
- **📦 一键解包**：内置 FModelCLI，自动从游戏 Pak 提取文本、语音和字体资源。

---

## 📚 项目文档 (Documentation)

### 📖 [用户手册 (User Guide)](docs/usage/)
- **[快速开始 (Quick Start)](docs/usage/quick-start.md)** - 5分钟完成环境配置与运行。
- **[数据管理 (Data Management)](docs/usage/data-management.md)** - 如何准备游戏文本与音频资源。

### 🛠️ [开发者指南 (Developer Guide)](docs/development/)
- **[贡献指南 (Contributing)](CONTRIBUTING.md)** - 参与项目开发流程。
- **[开发路线 (Roadmap)](docs/development/roadmap.md)** - 待实现功能与版本计划。

### 核心设计 (Technical Design)
- **[系统架构 (Architecture)](docs/design/architecture.md)** - 模块化设计与数据链路。
- **[OCR 引擎 (OCR System)](docs/design/ocr-system.md)** - 多后端选择与回退策略。
- **[语音播放 (Audio System)](docs/design/audio-system.md)** - Wwise Hash 算法与转码逻辑。

---

## 📦 快速启动

1. **环境准备**：确保安装了 Python 3.10+。
2. **克隆项目**：`git clone ...`
3. **一键初始化**：运行 `.\setup.ps1`（创建虚拟环境、安装依赖）。
4. **解包数据**：运行后在菜单点击 "Update Database" 或执行 `python -m ludiglot pak-update`。
5. **启动程序**：执行 `.\run.ps1` (PowerShell) 或 `run.bat` (CMD)。

*详见 **[快速开始指南](docs/usage/quick-start.md)** 获取完整步骤。*

---

## 📁 核心目录结构

```text
Ludiglot/
├── src/ludiglot/       # 源代码架构（Core/UI/Adapters）
├── docs/               # 标准化文档库
├── tools/              # 第三方工具（FModelCLI, wwiser 等）
├── config/             # 项目配置文件
├── cache/              # 运行缓存（数据库、音频缓存）
└── data/               # 外部数据目录
    ├── ConfigDB/       # 游戏配置数据
    ├── TextMap/        # 游戏文本数据
    ├── WwiseAudio_Generated/  # 游戏音频资源
    └── Fonts/          # 提取的游戏字体
```

---

## 🤝 贡献与致谢

欢迎所有形式的贡献！无论是 Bug 提交还是特性提案。

- 核心框架：[PyQt6](https://www.riverbankcomputing.com/software/pyqt/)
- 资源提取：[FModelCLI](https://github.com/Herselfta/FModelCLI) (基于 [FModel](https://github.com/4sval/FModel) / [CUE4Parse](https://github.com/FabianFG/CUE4Parse))
- 数据来源：[ClostroOffi/wuwa-aes-archive](https://github.com/ClostroOffi/wuwa-aes-archive)
- 工具组件：`vgmstream`, `wwiser`, `PaddleOCR`

---

<div align="center">

**⭐ 如果觉得项目有用，请给个 Star 支持一下！**

Made with ❤️ by the Ludiglot Community

</div>
