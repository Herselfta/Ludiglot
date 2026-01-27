# 数据源与路径管理指南

## 用户需要准备的数据

### 1. 游戏文本数据（必需）

Ludiglot 支持两种数据源：

**A. 从本地游戏 Pak 自动解包（推荐）**

- **来源**：本机已安装的鸣潮游戏资源
- **解包工具**：内置 CUE4Parse 解包器（自包含发布，无需安装依赖）
- **AES 密钥**：自动从 [ClostroOffi/wuwa-aes-archive](https://github.com/ClostroOffi/wuwa-aes-archive) 读取
- **可选语言**：会列出 `Client/Content/Aki/ConfigDB` 与 `TextMap` 下的语言文件夹供选择

> **首次使用**：首次运行 `pak-update` 时会自动发布解包器（约 60MB，仅首次需要，用户无需手动操作）

**B. 使用 Dimbreath/WutheringData（兼容旧流程）**

**来源**：[Dimbreath/WutheringData](https://github.com/Dimbreath/WutheringData)

**建议位置**：`data/WutheringData/`

**获取方式**：
```bash
cd data
git clone https://github.com/Dimbreath/WutheringData.git
```

**所需文件**：
- `TextMap/en/MultiText.json` - 英文文本
- `TextMap/zh-Hans/MultiText.json` - 中文文本

### 2. 游戏音频资源（可选，用于语音播放）

**来源**：推荐和文本数据一样，直接从游戏 Pak 解包（支持选择语音语言）。

**所需目录**：
- `Client/Content/Aki/WwiseAudio_Generated/Media/<lang>/`（.wem）
- `Client/Content/Aki/WwiseAudio_Generated/Event/<lang>/`（.bnk）

> 旧版 FModel 导出流程仍可使用，但不会再作为默认方案。

### 3. 音频转换工具 (vgmstream)

**作用**：将游戏原始 `.wem` 格式转为程序可播放的 `.wav`。

**获取方式（二选一）**：
1.  **复用 FModel (推荐)**：如果你已安装 FModel，Ludiglot 可以自动从 FModel 的内部目录提取 vgmstream。只需在配置中设置 `fmodel_root`。
2.  **手动下载**：从 [vgmstream release](https://github.com/vgmstream/vgmstream/releases) 下载 Windows 版本，解压到项目根目录的 `tools/vgmstream/` 下，确保包含 `vgmstream-cli.exe`。

---

## 路径规范

### 配置文件中的路径（使用相对路径）

```json
{
   "use_game_paks": true,
   "game_install_root": "D:/Games/Wuthering Waves",
   "pak_extractor": "cue4parse",
   "cue4parse_extractor_path": null,
   "game_platform": "Windows",
   "game_server": "CN",
   "game_version": "2.8",
   "game_languages": ["en", "zh-Hans"],
   "game_audio_languages": ["zh"],
   "unrealpak_path": "C:/Program Files/Epic Games/UE_4.26/Engine/Binaries/Win64/UnrealPak.exe",
   "data_root": "data/GameData",
   "audio_wem_root": "data/GameAudio/Client/Content/Aki/WwiseAudio_Generated/Media/zh",
   "audio_bnk_root": "data/GameAudio/Client/Content/Aki/WwiseAudio_Generated/Event/zh",
   "audio_cache_path": "cache/audio",
   "vgmstream_path": null
}
```

### 运行时处理（自动转换为绝对路径）

- **Windows OCR 要求**：必须使用绝对路径（如 `C:\Users\...\img.jpg`）
- **自动处理**：代码会自动将相对路径转换为绝对路径
- **用户无需关心**：配置文件中只需使用相对路径即可

### 语言包依赖（Windows OCR）

**要求**：Windows 系统必须安装对应语言包

- 识别英文：需要"英语"语言包
- 识别中文：需要"中文(简体)"语言包

**检查方式**：
1. 打开 Settings（设置）
2. Time & Language → Language（时间和语言 → 语言）
3. 确认已安装"English (United States)"和"中文(简体，中国)"

**启动检测**：程序启动时会自动检测并提示缺失的语言包

---

## Ludiglot 的职责

### 数据处理
1. **构建索引**：从 WutheringData 构建搜索数据库（`cache/game_text_db.json`）
2. **转换音频**：使用 vgmstream 将 `.wem` 转为 `.wav`/`.ogg`
3. **缓存管理**：在 `cache/audio/` 管理转换后的音频

### 数据隔离
- **不追踪用户数据**：所有 `data/`, `cache/` 目录在 `.gitignore` 中排除
- **配置文件保护**：`config/settings.json` 不会被提交到 Git
- **私有文档保护**：`PrivateDevDoc/` 仅用于开发，不会公开

---

## 目录结构

```
Ludiglot/
├── data/                          # 用户数据（不追踪）
│   ├── GameData/                  # 从游戏 Pak 解包的文本数据
│   │   ├── TextMap/
│   │   └── ConfigDB/
│   └── GameAudio/                 # 从游戏 Pak 解包的语音资源
│       └── Client/Content/Aki/WwiseAudio_Generated/
│           ├── Media/zh/
│           └── Event/zh/
├── cache/                         # 运行时缓存（不追踪）
│   ├── capture.png                # OCR 截图
│   ├── game_text_db.json          # 构建的文本数据库
│   └── audio/                     # 转换后的音频缓存
│       ├── audio_index.json       # 音频索引
│       ├── txtp/                  # TXTP 缓存
│       └── *.wav/*.ogg            # 转换后的音频文件
├── config/
│   ├── settings.example.json      # 配置模板（追踪）
│   └── settings.json              # 用户配置（不追踪）
└── PrivateDevDoc/                 # 私有开发文档（不追踪）
```

---

## 注意事项

### Windows OCR 特殊要求

1. **绝对路径**：`storage.StorageFile.get_file_from_path_async` 要求绝对路径
   - ✅ 正确：`C:\Users\Username\Ludiglot\cache\capture.png`
   - ❌ 错误：`./cache/capture.png`

2. **语言包检查**：OcrEngine 只能识别已安装语言包的语言
   - 程序启动时会自动检测
   - 缺失时会提供安装指引

3. **内存流转换**（待实现）：
   - 当前：截图保存到硬盘 → OCR 读取文件
   - 优化：截图保持在内存 → 内存流 → OCR
   - 逻辑：`OpenCV/PIL Image → Bytes → InMemoryRandomAccessStream → BitmapDecoder → OCR`

### 数据更新流程

1. **Pak 数据更新（推荐）**：
   ```bash
   python -m ludiglot pak-update --config config/settings.json
   ```

2. **旧版 WutheringData 更新**：
   ```bash
   cd data/WutheringData
   git pull
   ```
