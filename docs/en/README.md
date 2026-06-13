<div align="center">

# 🌐 Ludiglot

**Intelligent Game Text Translation Assistant | Real-time OCR + Voice Playback**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](../LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows)](https://www.microsoft.com/windows)

[English](README.md) | [简体中文](../../README.md)

</div>

---

## ✨ Features

- **🔍 Smart OCR**: Powered by Windows native OCR engine, fast start-up, fully local, lightweight and low memory usage.
- **🌏 Instant Translation**: Non-intrusive overlay displays official Chinese text
- **🎵 Voice Playback**: Auto-play corresponding official voice-over with Wwise logic
- **⌨️ Global Hotkeys**: Hotkey screenshot and smart title separation
- **📦 One-Click Extraction**: Built-in FModelCLI for auto-extracting text, audio, and fonts from game Pak

---

## 📦 Quick Start

1. **Prerequisites**: Python 3.10+ installed
2. **Clone**: `git clone ...`
3. **Setup**: Run `.\setup.ps1` (creates venv, installs dependencies)
4. **Configure**: Edit `config/settings.json` with your game path, server, and languages
5. **Rebuild Data**: Run `.\.venv\Scripts\python.exe -m ludiglot pak-update`
6. **Run**: Execute `.\run.ps1`

---

## 📁 Directory Structure

```text
Ludiglot/
├── src/ludiglot/       # Source code (Core/UI/Adapters)
├── docs/               # Documentation
├── tools/              # Third-party tools (FModelCLI, wwiser, etc.)
├── config/             # Configuration files
├── cache/              # Runtime cache (database, audio cache)
└── data/               # Extracted data
    ├── ConfigDB/       # Game config data
    ├── TextMap/        # Game text data
    ├── WwiseAudio_Generated/  # Game audio assets
    └── Fonts/          # Extracted game fonts
```

---

## 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](../../CONTRIBUTING.md) for details.

## 📜 License

This project is licensed under the [MIT License](../../LICENSE).

## 🙏 Acknowledgments

- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - GUI framework
- [FModelCLI](https://github.com/Herselfta/FModelCLI) - Pak extraction (based on FModel/CUE4Parse)
- [yarik0chka/wuwa-keys](https://github.com/yarik0chka/wuwa-keys) - AES keys
- [vgmstream](https://github.com/vgmstream/vgmstream) - Game audio decoder

---

<div align="center">

**⭐ If you find this project useful, please give it a star!**

Made with ❤️ by the Ludiglot Community

</div>
