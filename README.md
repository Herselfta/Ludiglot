<div align="center">

# 🌐 Ludiglot

**智能游戏文本翻译助手 | 实时 OCR + 语音播放**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows)](https://www.microsoft.com/windows)
[![Docs](https://img.shields.io/badge/docs-standard-green)](docs/README.md)

[English](docs/en/README.md) | 简体中文

</div>

---

## ✨ 特性一览

- **🔍 智能 OCR**：Windows 原生 OCR 优先，秒级启动。智能回退 PaddleOCR/Tesseract 机制。
- **🌏 即时翻译**：非侵入式复刻《鸣潮》风格覆盖层，实时检索官方文本。
- **🎵 原声语音**：自动定位并播放对应官方语音，支持 Wwise 逻辑推导。
- **⌨️ 全局集成**：热键截图、历史记录、智能标题分离一应俱全。

---

## 📚 项目文档 (Documentation)

按标准开源规范整理，请根据需求查阅：

### 📖 [用户手册 (User Guide)](docs/usage/)
- **[快速开始 (Quick Start)](docs/usage/quick-start.md)** - 5分钟完成环境配置与运行。
- **[数据管理 (Data Management)](docs/usage/data-management.md)** - 如何准备游戏文本与音频资源。

### 核心设计 (Technical Design)
- **[系统架构 (Architecture)](docs/design/architecture.md)** - 模块化设计与数据链路。
- **[OCR 引擎 (OCR System)](docs/design/ocr-system.md)** - 多后端选择与回退策略。
- **[语音播放 (Audio System)](docs/design/audio-system.md)** - Wwise Hash 算法与转码逻辑。

### 🛠️ [开发者指南 (Developer Guide)](docs/development/)
- **[贡献指南 (Contributing)](CONTRIBUTING.md)** - 参与项目开发流程。
- **[测试文档 (Testing Guide)](docs/development/testing.md)** - 环境验证与 OCR 压力测试。
- **[开发路线 (Roadmap)](docs/development/roadmap.md)** - 待实现功能与版本计划。

---

## 📦 快速启动

1. **环境准备**：确保安装了 Python 3.10+。
2. **克隆项目**：`git clone ...`
3. **放置数据**：将 `WutheringData` 放入 `data/` 目录。
4. **运行脚本**：执行 `.\run.ps1` (PowerShell) 或 `run.bat` (CMD)。

*详见 **[快速开始指南](docs/usage/quick-start.md)** 获取完整步骤。*

---

## 📁 核心目录结构

```text
Ludiglot/
├── src/ludiglot/       # 源代码架构（Core/UI/Adapters）
├── docs/               # 标准化文档库
├── tools/              # 第三方工具（vgmstream, wwiser 等）
├── config/             # 项目配置文件
├── cache/              # 运行缓存（已忽略内容，保留结构）
└── data/               # 外部数据目录（README 指引）
```

---

## 🤝 贡献与致谢

欢迎所有形式的贡献！无论是 Bug 提交还是特性提案。

- 核心框架：[PyQt6](https://www.riverbankcomputing.com/software/pyqt/)
- 数据来源：[Dimbreath/WutheringData](https://github.com/Dimbreath/WutheringData)
- 工具组件：`vgmstream`, `wwiser`, `PaddleOCR`

---

<div align="center">

**⭐ 如果觉得项目有用，请给个 Star 支持一下！**

Made with ❤️ by the Ludiglot Community

</div>
