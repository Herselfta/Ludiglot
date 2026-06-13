# 快速开始 (Quick Start)

本文档帮助新用户在 Windows 环境下从零开始安装、配置、完全重建游戏数据并启动 Ludiglot。

## 1. 环境准备

请先安装：

1. **Git**：用于克隆项目。([下载 Git](https://git-scm.com/downloads))
2. **Python 3.10+**：项目运行环境。([下载 Python](https://www.python.org/downloads/))
   - 安装时建议勾选 **Add Python to PATH**。

> Pak 解包器使用自包含 FModelCLI，用户不需要安装 .NET SDK。

## 2. 获取项目

打开 PowerShell，执行：

```powershell
git clone https://github.com/yourusername/Ludiglot.git
cd Ludiglot
```

## 3. 初始化环境

在项目根目录运行：

```powershell
.\setup.ps1
```

脚本会自动：

- 创建 Python 虚拟环境 `.venv`。
- 安装 OCR、GUI、音频等依赖。
- 生成 `config/settings.json`。

如果 PowerShell 提示禁止运行脚本，请先执行：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

然后重新运行 `setup.ps1`。

## 4. 配置游戏路径

编辑 `config/settings.json`，重点确认下面这些字段：

```json
{
  "use_game_paks": true,
  "game_install_root": "D:/Games/Wuthering Waves/Wuthering Waves Game",
  "game_platform": "Windows",
  "game_server": "OS",
  "game_languages": ["en", "zh-Hans"],
  "game_audio_languages": ["zh"],
  "extract_audio": true,
  "data_root": "data",
  "db_path": "cache/game_text_db.json"
}
```

`game_install_root` 应指向包含 `Client` 文件夹的游戏根目录，例如：

```text
Wuthering Waves Game/
└── Client/
```

不要填启动器目录，也不要填到 `Client` 子目录内部。

## 5. 完全重建游戏数据

首次使用必须先从本地游戏 Pak 构建 Ludiglot 数据库。

推荐直接运行：

```powershell
.\.venv\Scripts\python.exe -m ludiglot pak-update
```

如果你已经激活虚拟环境，也可以运行：

```powershell
python -m ludiglot pak-update
```

程序会自动：

1. 获取 AES 密钥。
2. 准备 FModelCLI。
3. 从游戏 Pak 提取 `ConfigDB`、`TextMap` 和字体。
4. 在 `extract_audio: true` 时提取语音资源。
5. 写回 `fonts_root`、`audio_wem_root`、`audio_bnk_root` 等配置。
6. 生成 `cache/game_text_db.json`。

看到下面这类输出即表示成功：

```text
[PAK] 数据库已保存: .../cache/game_text_db.json (... 条)
✅ Pak 更新完成
```

> 也可以首次启动后在覆盖层菜单点击 **Update Database**，但命令行更适合新用户确认完整输出。

## 6. 启动程序

重建完成后运行：

```powershell
.\run.ps1
```

也可以双击根目录下的 `run.bat`。

## 7. 后续更新

游戏版本更新后，再运行一次：

```powershell
.\.venv\Scripts\python.exe -m ludiglot pak-update
```

通常不需要手动清空 `data/` 或 `cache/`。如果出现文本缺失、音频路径异常或想彻底重建，请参考 [数据管理指南](data-management.md) 的“完全重新构建数据”。

---

## 常见问题

**Q: `setup.ps1` 提示“在此系统上禁止运行脚本”？**

A: 这是 PowerShell 执行策略限制。运行：

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

然后重新执行 `setup.ps1`。

**Q: 解包时提示找不到游戏安装目录？**

A: 检查 `game_install_root`，它必须指向包含 `Client` 文件夹的游戏根目录，而不是启动器目录。

**Q: AES 密钥获取失败？**

A: 首次重建需要联网获取 AES 表。成功后会缓存到 `cache/aes_archive.md`；如果网络失败且没有缓存，请检查网络后重试。

**Q: 重建后没有语音？**

A: 确认 `extract_audio` 为 `true`，`game_audio_languages` 包含要播放的语音语言，例如 `zh`，并确认 `pak-update` 成功写回 `audio_wem_root` 和 `audio_bnk_root`。

**Q: 启动后提示找不到 OCR 语言包？**

A: Windows 原生 OCR 需要系统语言包。打开 **设置 > 时间和语言 > 语言和区域**，安装 **English (United States)**；如需中文 OCR，也安装 **中文(简体，中国)**。

**Q: 为什么游戏内匹配经常失败、漏匹配或不播语音？**

A: **请确保您的 Windows OCR 语言包已正确安装且识别框大小合适**。目前的匹配系统完全基于本地高速的 Windows 原生 OCR。由于去除了复杂的深度学习大模型，如果出现匹配失败，请检查：
1. 游戏字幕区域是否被正确框选。
2. Windows 系统中是否安装了当前翻译源语言（如 English）的 OCR 功能包。
3. 调整游戏分辨率或缩放，以获得最清晰的字符边缘。
