# 数据源与路径管理指南

## 用户需要准备的数据

### 1. 游戏文本数据（必需）

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

**更新方式**：
```bash
cd data/WutheringData
git pull
```

### 2. 游戏音频资源（可选，用于语音播放）

**来源**：使用 FModel 从游戏目录提取

**AES 密钥**：参考 [ClostroOffi/wuwa-aes-archive](https://github.com/ClostroOffi/wuwa-aes-archive)

**建议位置**：`data/FModelExports/`

**所需文件**：
- `.wem` 文件（音频）→ `Client/Content/Aki/WwiseAudio_Generated/Media/zh/`
- `.bnk` 文件（事件映射）→ `Client/Content/Aki/WwiseAudio_Generated/Event/zh/`

**提取步骤**：
1. 下载并安装 [FModel](https://fmodel.app/)
2. 从 wuwa-aes-archive 获取最新 AES 密钥
3. 在 FModel 中挂载游戏目录
4. 导出 WwiseAudio 相关文件到 `data/FModelExports/`

---

## 路径规范

### 配置文件中的路径（使用相对路径）

```json
{
  "data_root": "data/WutheringData",
  "audio_cache_path": "cache/audio",
  "audio_wem_root": "data/FModelExports/Client/Content/Aki/WwiseAudio_Generated/Media/zh",
  "audio_bnk_root": "data/FModelExports/Client/Content/Aki/WwiseAudio_Generated/Event/zh"
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
│   ├── WutheringData/             # 游戏文本数据（Git 仓库）
│   │   └── TextMap/
│   │       ├── en/MultiText.json
│   │       └── zh-Hans/MultiText.json
│   └── FModelExports/             # FModel 导出的游戏资源
│       └── Client/Content/Aki/WwiseAudio_Generated/
│           ├── Media/zh/          # .wem 音频文件
│           └── Event/zh/          # .bnk 事件文件
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

1. **文本数据更新**：
   ```bash
   cd data/WutheringData
   git pull
   # 重启 Ludiglot，会自动重建数据库
   ```

2. **音频资源更新**：
   - 游戏更新后，重新使用 FModel 导出
   - 删除 `cache/audio/` 目录
   - 重启 Ludiglot，会重新转换音频
