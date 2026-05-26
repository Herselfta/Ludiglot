# 数据源与路径管理指南

本文档面向从零开始或想完全重建数据的用户。Ludiglot 不需要手动下载 WutheringData；推荐使用内置 `pak-update` 流程，直接从本机《鸣潮》游戏 Pak 提取文本、语音和字体。

## 一句话流程

1. 确认游戏已安装并能正常启动。
2. 在 `config/settings.json` 配置 `game_install_root`、区服和语言。
3. 运行 `python -m ludiglot pak-update`。
4. 启动 `.un.ps1`。

如果你刚运行过 `setup.ps1` 且没有激活虚拟环境，也可以使用：

```powershell
.\.venv\Scripts\python.exe -m ludiglot pak-update
```

---

## 完全重新构建数据

当游戏更新、文本缺失、音频匹配异常，或你想清空旧解包结果时，按下面流程操作。

### 1. 关闭 Ludiglot

先关闭覆盖层窗口，避免程序正在读取数据库或音频缓存。

### 2. 确认配置

编辑 `config/settings.json`，至少确认这些字段：

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
  "db_path": "cache/game_text_db.json",
  "audio_cache_path": "cache/audio"
}
```

| 配置项 | 说明 |
|--------|------|
| `game_install_root` | 游戏安装目录，应指向包含 `Client` 文件夹的目录，例如 `.../Wuthering Waves Game` |
| `game_platform` | 平台：`Windows` / `Android` / `iOS` |
| `game_server` | 区服：`OS` 国际服 / `CN` 国服 |
| `game_languages` | 要提取的文本语言；推荐至少包含 `en` 和 `zh-Hans` |
| `game_audio_languages` | 要提取的语音语言；中文语音通常为 `zh` |
| `extract_audio` | 是否同时提取语音资源；只想重建文本可设为 `false` |
| `data_root` | 解包后的原始数据目录，默认 `data` |
| `db_path` | 搜索数据库输出路径，默认 `cache/game_text_db.json` |
| `audio_cache_path` | 转换后的可播放音频缓存目录，默认 `cache/audio` |

> `pak-update` 成功后会自动写回 `fonts_root`、`audio_wem_root`、`audio_bnk_root` 等路径；通常不需要手动填写这些输出路径。

### 3. 可选：备份旧数据

如果你想做“干净重建”，建议先把旧目录改名备份，而不是直接删除：

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
if (Test-Path "data") { Rename-Item "data" "data.backup-$stamp" }
if (Test-Path "cache\game_text_db.json") { Rename-Item "cache\game_text_db.json" "game_text_db.backup-$stamp.json" }
if (Test-Path "cache\audio") { Rename-Item "cache\audio" "audio.backup-$stamp" }
```

只重建文本时，可以不备份 `cache/audio`；这样已转换的 `.wav` 音频缓存还能复用。

### 4. 运行重建命令

```powershell
.\.venv\Scripts\python.exe -m ludiglot pak-update
```

如果你已经激活虚拟环境，也可以运行：

```powershell
python -m ludiglot pak-update
```

GUI 中也可以点击覆盖层菜单 **Update Database**，效果相同。

### 5. 等待输出完成

程序会自动执行：

1. 获取 AES 密钥；网络失败时会尝试使用 `cache/aes_archive.md` 本地缓存。
2. 确认平台、区服和语言。
3. 自动准备 FModelCLI。
4. 从游戏 Pak 提取：
   - `ConfigDB/`
   - `TextMap/`
   - `Config/Json`
   - `UI/Framework/LGUI/Font/`
   - 语音资源 `Event/<lang>/`、`Media/<lang>/`、`WwiseExternalSource/<lang>_`（当 `extract_audio: true`）
5. 整理目录结构到 `data/` 根目录。
6. 写回配置文件中的字体和音频资源路径。
7. 构建 `cache/game_text_db.json`。

看到类似下面输出即可认为重建成功：

```text
[PAK] 数据库已保存: .../cache/game_text_db.json (... 条)
✅ Pak 更新完成
```

---

## 重建后的目录结构

```text
Ludiglot/
├── data/
│   ├── ConfigDB/                  # 游戏配置数据
│   │   └── <lang>/
│   ├── TextMap/                   # 游戏文本数据
│   │   └── <lang>/
│   ├── Config/                    # 通用配置 JSON
│   ├── WwiseAudio_Generated/      # 游戏语音资源（extract_audio=true 时）
│   │   ├── Media/<lang>/          # .wem 文件
│   │   └── Event/<lang>/          # .bnk 文件
│   └── Fonts/                     # 游戏字体
├── cache/
│   ├── game_text_db.json          # 本地搜索数据库
│   ├── aes_archive.md             # AES 密钥缓存
│   └── audio/                     # 转换后的可播放音频缓存
│       ├── audio_index.json
│       └── *.wav
├── config/
│   ├── settings.example.json
│   └── settings.json
└── tools/
    ├── FModelCLI.exe              # 自动准备的解包工具
    └── .data/
        └── vgmstream-cli.exe      # FModelCLI 管理的音频转换工具
```

---

## 首次启动与后续更新

### 首次启动

完全重建完成后运行：

```powershell
.\run.ps1
```

程序会读取 `cache/game_text_db.json`，并按需扫描 `cache/audio`。

### 游戏版本更新后

游戏更新后重新运行：

```powershell
.\.venv\Scripts\python.exe -m ludiglot pak-update
```

通常不需要手动清空目录；如果出现文本缺失、语言错乱或音频路径异常，再按“完全重新构建数据”的备份流程做干净重建。

---

## 常见问题

### 提示找不到游戏安装目录

检查 `game_install_root` 是否指向包含 `Client` 文件夹的目录。常见结构类似：

```text
Wuthering Waves Game/
└── Client/
```

不要只填启动器目录，也不要填到 `Client` 子目录内部。

### AES 密钥获取失败

首次运行需要联网获取 AES 表。若网络失败且没有本地缓存，重建会失败。可以稍后重试；成功获取后会缓存到 `cache/aes_archive.md`。

### FModelCLI 或 vgmstream 缺失

通常不需要手动安装。Ludiglot 会自动准备 `tools/FModelCLI.exe`，FModelCLI 会自动管理 `tools/.data/vgmstream-cli.exe`。

如果自动下载受限，请先检查网络代理或手动确认 `tools/` 目录是否可写。也可以手动下载：

1. 打开 `https://github.com/Herselfta/FModelCLI/releases/latest`
2. 下载 `FModelCLI.exe`
3. 放到项目目录的 `tools/FModelCLI.exe`

### 重建后没有语音

确认：

1. `extract_audio` 是 `true`。
2. `game_audio_languages` 包含你想播放的语音语言，例如 `zh`。
3. `pak-update` 成功写回了 `audio_wem_root` 和 `audio_bnk_root`。
4. 启动后日志中没有音频缓存扫描或转码错误。

### 只想重建文本，不想提取音频

把配置改为：

```json
{
  "extract_audio": false
}
```

然后重新运行 `pak-update`。这样会更快，但不会更新语音资源。

### Windows OCR 语言包缺失

Windows 原生 OCR 需要系统安装对应语言包：

1. 打开 **设置 > 时间和语言 > 语言和区域**。
2. 安装 **English (United States)**。
3. 如果需要中文 OCR，也安装 **中文(简体，中国)**。

OCR 语言包和 `pak-update` 不是同一个步骤；数据重建成功后，OCR 仍可能因为系统语言包缺失而无法识别截图。
