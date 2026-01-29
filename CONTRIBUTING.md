---

## 🤝 贡献指南

欢迎贡献代码、报告问题或提出建议！

### 开发流程

1. **Fork 本仓库**
2. **创建特性分支**: `git checkout -b feature/AmazingFeature`
3. **提交更改**: `git commit -m 'Add some AmazingFeature'`
4. **推送分支**: `git push origin feature/AmazingFeature`
5. **提交 Pull Request**

### 代码规范

- 使用 **Black** 格式化代码
- 使用 **mypy** 进行类型检查
- 添加必要的文档字符串

### 架构与开发规范 (Architecture & Guidelines)

为了保持代码的高可维护性和逻辑的统一，本项目遵循严格的开发规范。在开始贡献之前，请务必阅读以下文档：

1.  **[开发原则与协作规范](docs/DEVELOPMENT_PRINCIPLES.md)**：包含核心分层原则、逻辑下沉要求以及 AI 协作协议。
2.  **[架构设计手册](docs/design/architecture.md)**：包含目录结构、模块职责以及数据流水线说明。

**核心红线**：禁止在 UI 层编写业务逻辑；禁止在根目录创建临时脚本。

### 报告问题

遇到 Bug？请[提交 Issue](https://github.com/yourusername/Ludiglot/issues) 并包含：

- 操作系统版本
- Python 版本
- 错误日志
- 复现步骤

---

## 📜 许可证

本项目采用 [MIT License](LICENSE) 许可。

---

## 🙏 致谢

### 核心依赖

- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - GUI 框架
- [Windows.Media.Ocr](https://docs.microsoft.com/en-us/uwp/api/windows.media.ocr) - Windows 原生 OCR
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) - 备选 OCR 引擎
- [vgmstream](https://github.com/vgmstream/vgmstream) - 游戏音频解码

### 工具支持

- [FModel](https://fmodel.app/) - 游戏资源提取
- [wwiser](https://github.com/bnnm/wwiser) - Wwise BNK 分析

---

## 📧 联系方式

- **项目主页**: [https://github.com/yourusername/Ludiglot](https://github.com/yourusername/Ludiglot)
- **问题反馈**: [Issues](https://github.com/yourusername/Ludiglot/issues)
- **讨论交流**: [Discussions](https://github.com/yourusername/Ludiglot/discussions)

---

<div align="center">

**⭐ 如果觉得项目有用，请给个 Star 支持一下！**

Made with ❤️ by Contributors

</div>
