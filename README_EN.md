<div align="center">

# 🌐 Ludiglot

**Intelligent Game Text Translation Assistant | Real-time OCR + Voice Playback**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows)](https://www.microsoft.com/windows)

[English](README_EN.md) | [简体中文](README.md)

</div>

---

## ✨ Features

- **🔍 Smart OCR**: Windows native OCR (startup < 0.1s, recognition ~0.05s) with auto-fallback
- **🎯 Mixed Content Recognition**: Intelligently distinguishes single-line titles from multi-line descriptions
- **🌏 Instant Translation**: Overlay window displays Chinese translation with title highlighting
- **🎵 Voice Playback**: Auto-play character voices (Hash/Event dual matching)
- **⌨️ Global Hotkeys**: `Alt+W` for quick screenshot, `Alt+Q` to toggle overlay

## 📦 Quick Start

### One-Click Installation (Recommended)

```bash
# 1. Clone repository
git clone https://github.com/yourusername/Ludiglot.git
cd Ludiglot

# 2. Setup environment (Windows)
.\setup.ps1        # PowerShell
# or
setup.bat          # CMD

# 3. Run application
.\run.ps1          # PowerShell
# or
run.bat            # CMD
```

### Manual Installation

```bash
# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # Windows PowerShell

# Install dependencies
pip install -e .

# Optional: Install Windows OCR
pip install winrt-Windows.Media.Ocr winrt-Windows.Graphics.Imaging winrt-Windows.Storage.Streams
```

## 🎮 Usage

### Configuration

Copy and edit the config file:

```bash
copy config\settings.example.json config\settings.json
```

### Launch GUI

```bash
python -m ludiglot
```

### CLI Commands

```bash
# Build text database
python -m ludiglot build --en MultiText_EN.json --zh MultiText_ZH.json

# OCR screenshot
python -m ludiglot ocr --image screenshot.png --db game_text_db.json

# Extract audio
python -m ludiglot audio-extract --wem-root /path/to/wem --cache audio_cache/
```

## 📁 Project Structure

```
Ludiglot/
├── src/ludiglot/
│   ├── core/              # Core modules (OCR, lookup, smart_match)
│   ├── adapters/          # Game adapters
│   └── ui/                # GUI interface
├── config/                # Configuration files
├── tools/                 # Utility tools
├── setup.ps1              # One-click setup script
└── run.ps1                # One-click run script
```

## 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📜 License

This project is licensed under the [MIT License](LICENSE).

## 🙏 Acknowledgments

- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) - GUI framework
- [Windows.Media.Ocr](https://docs.microsoft.com/en-us/uwp/api/windows.media.ocr) - Windows OCR
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) - Alternative OCR engine
- [vgmstream](https://github.com/vgmstream/vgmstream) - Game audio decoder
- [FModel](https://fmodel.app/) - Game resource extractor
- [WutheringData](https://github.com/Dimbreath/WutheringData) - Wuthering Waves game text and audio database

---

<div align="center">

**⭐ If you find this project useful, please give it a star!**

Made with ❤️ by the Ludiglot Community

</div>
