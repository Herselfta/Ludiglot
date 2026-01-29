# 数据源与路径管理指南

## 用户需要准备的数据

### 1. 游戏文本数据（必需）

Ludiglot 直接从本地游戏 Pak 解包数据，无需手动下载。

**解包方式**：
- 运行 `python -m ludiglot pak-update`
- 或在程序菜单点击 **Update Database**

**自动处理**：
- **AES 密钥**：自动从 [ClostroOffi/wuwa-aes-archive](https://github.com/ClostroOffi/wuwa-aes-archive) 获取
- **解包工具**：内置 FModelCLI（自包含发布，无需安装依赖）
- **语言选择**：根据配置文件中的 `game_languages` 提取对应语言

**输出目录**：
- `data/ConfigDB/` - 游戏配置数据
- `data/TextMap/` - 游戏文本数据

### 2. 游戏音频资源（可选）

在配置中设置 `extract_audio: true` 后，解包时会自动提取语音资源。

**输出目录**：
- `data/WwiseAudio_Generated/Media/<lang>/` - .wem 音频文件
- `data/WwiseAudio_Generated/Event/<lang>/` - .bnk 事件映射

### 3. 游戏字体（自动提取）

解包时会自动提取游戏内字体：
- `data/Fonts/H7GBKHeavy.ttf`
- `data/Fonts/LaguSansBold.ttf`
- 以及其他 `.ufont` 文件（自动转换为 `.ttf`）

### 4. 音频转换工具 (vgmstream)

**作用**：将游戏原始 `.wem` 格式转为程序可播放的 `.wav`。

**获取方式**：
- FModelCLI 会自动下载并管理 vgmstream 到 `tools/.data/` 目录
- 无需手动配置

---

## 配置文件说明

### 核心配置项

```json
{
  "use_game_paks": true,
  "game_install_root": "D:/Games/Wuthering Waves Game",
  "game_platform": "Windows",
  "game_server": "OS",
  "game_languages": ["en", "zh-Hans"],
  "game_audio_languages": ["zh"],
  "extract_audio": true,
  "data_root": "data",
  "fonts_root": "data/Fonts"
}
```

| 配置项 | 说明 |
|--------|------|
| `use_game_paks` | 是否从游戏 Pak 解包数据 |
| `game_install_root` | 游戏安装目录（包含 `Client` 文件夹） |
| `game_platform` | 平台：Windows / Android / iOS |
| `game_server` | 区服：OS（国际服）/ CN（国服） |
| `game_languages` | 文本语言列表 |
| `game_audio_languages` | 语音语言列表 |
| `extract_audio` | 是否解包语音资源 |
| `data_root` | 数据输出根目录 |
| `fonts_root` | 字体目录 |

### 路径处理

- **配置文件**：使用相对路径（如 `data/Fonts`）
- **运行时**：自动转换为绝对路径
- **Windows OCR**：要求绝对路径，程序自动处理

---

## 目录结构

```
Ludiglot/
├── data/                          # 用户数据（不追踪）
│   ├── ConfigDB/                  # 游戏配置数据
│   │   └── <lang>/
│   ├── TextMap/                   # 游戏文本数据
│   │   └── <lang>/
│   ├── WwiseAudio_Generated/      # 游戏音频资源
│   │   ├── Media/<lang>/          # .wem 文件
│   │   └── Event/<lang>/          # .bnk 文件
│   └── Fonts/                     # 游戏字体
│       ├── H7GBKHeavy.ttf
│       └── LaguSansBold.ttf
├── cache/                         # 运行时缓存（不追踪）
│   ├── game_text_db.json          # 构建的文本数据库
│   ├── aes_archive.md             # AES 密钥缓存
│   └── audio/                     # 转换后的音频缓存
│       ├── audio_index.json
│       └── *.wav
├── config/
│   ├── settings.example.json      # 配置模板（追踪）
│   └── settings.json              # 用户配置（不追踪）
└── tools/
    ├── FModelCLI.exe              # 解包工具
    └── .data/                     # 工具依赖
        └── vgmstream-cli.exe
```

---

## 数据更新流程

游戏版本更新后，只需重新运行解包命令：

```bash
python -m ludiglot pak-update
```

或在程序菜单点击 **Update Database**。

程序会自动：
1. 获取最新 AES 密钥
2. 增量更新数据
3. 重建搜索数据库

---

## Windows OCR 语言包

Windows 原生 OCR 需要系统安装对应语言包：

1. 打开 **设置 > 时间和语言 > 语言和区域**
2. 确认已安装：
   - **English (United States)** - 英文识别
   - **中文(简体，中国)** - 中文识别

程序启动时会自动检测并提示缺失的语言包。
