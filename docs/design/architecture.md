# Project Manifest: Ludiglot

**Architecture:** Modular Core + Game Adapter  
**Target:** Immersive Language Learning Tool for Wuthering Waves

## 1. Project Vision & Philosophy

我们要构建一个**非侵入式、原生体验**的语言学习引擎。它不仅仅是一个翻译器，而是一个"游戏伴侣"，能够让玩家在不脱离游戏沉浸感的前提下，通过 OCR 逆向检索官方文本和语音，实现母语级的剧情理解。

### Core Principles

1. **Safe & External**: 坚持使用 OCR 和外部数据库，严禁内存读写（Anti-Cheat Compliance）。
2. **Native Fidelity**:
   * **Text**: 必须显示官方汉化文本，拒绝机翻。
   * **Audio**: 必须能够播放对应的官方语音。
   * **Visual**: UI 必须复刻《鸣潮》原生科技风，与游戏界面无缝融合。
3. **Automated**: 数据源自动追踪上游，实现"零维护"更新。

---

## 2. System Architecture (Micro-Kernel)

系统采用 **Core (通用内核)** + **Adapter (游戏适配器)** 模式。

### Module A: The Core (GlotGame Engine)

*通用组件，不包含特定游戏逻辑。*

* **Infrastructure**: 工具管理器（FModelCLI, vgmstream）。
* **Vision**: OCR 引擎（支持 Windows OCR 与高精度的 PaddleOCR-VL-1.6 视觉语言多模态模型）。
* **Search**: `RapidFuzz` 模糊匹配引擎。
* **UI**: 基于 `PyQt6` 的覆盖层系统，支持 QSS 样式表定制。

### Module B: The Adapter (`adapters/wuthering_waves`)

*《鸣潮》特化逻辑。*

* **Data Mapper**: 解析 ConfigDB 和 TextMap 数据。
* **Audio Strategy**: 实现 `vo_` 前缀 + Wwise Hash 计算逻辑。
* **Asset Extractor**: 基于 FModelCLI 的自动解包。

---

## 3. Data Engineering & Logic

### 3.1 Text Pipeline (TextMap)

* **Source**: 从游戏 Pak 解包的 `TextMap/<lang>/MultiText.json`
* **Logic**:
  * 建立映射：`TextKey` → `Chinese Text`
  * 建立索引：`Normalized English` → `TextKey`
  * 支持多语言：en, zh-Hans, ja, ko 等

### 3.2 PAK Extraction Strategy

#### FModelCLI 工作模式

```csharp
// FModelCLI/Program.cs L158
var provider = new DefaultFileProvider(
    gameDir,                          // E:/Wuthering Waves/Wuthering Waves Game
    SearchOption.AllDirectories,      // 递归扫描所有子目录
    version, 
    StringComparer.OrdinalIgnoreCase
);
provider.Mount();  // 挂载所有找到的 PAK
```

**扫描范围**：
- `Content/Paks/*.pak` - 基础游戏资源
- `Content/Paks/pakchunk0-WindowsNoEditor.pak` - 主要数据包
- `Saved/Resources/<ver>/Resource/*.pak` - 增量补丁

#### CUE4Parse PAK 合并策略

**问题核心**：当多个 PAK 包含同一虚拟路径时的导出行为

```
基础 PAK  (pakchunk2-WindowsNoEditor.pak):   ReadOrder = 3      (EN 字段为空)
补丁 PAK  (pakchunk2-WindowsNoEditor_P.pak): ReadOrder = 103    (EN 字段完整)
```

**CUE4Parse 内部优先级**（源码分析 `FileProviderDictionary.cs`）：

| API | 行为 | 结果 |
|-----|------|------|
| `TryGetValue(key)` | `OrderByDescending(ReadOrder)` 首个匹配即返回 | ✅ 补丁 (103) 正确胜出 |
| `GetEnumerator()` | `OrderByDescending(ReadOrder)` 遍历所有 bag，yield 每条条目，**不去重** | ⚠️ 同一路径出现两次 |

`ReadOrder` 计算（`AbstractVfsReader.VerifyReadOrder()`）：
- 基础 PAK: `GetPakOrderFromPakFilePath() = 3`
- 补丁 `_P.pak`: `3 + 100 × (versionNumber + 1) = 103`（补丁始终更高）

**旧 FModelCLI 的 bug**：
```csharp
foreach (var file in provider.Files)   // GetEnumerator(): 补丁条目先出，基础条目后出
    File.WriteAllBytes(outPath, ...);  // 后写覆盖先写 → 基础版本覆盖补丁版本
```

#### 修复方案：FModelCLI ReadOrder 去重（v1.1.0）

```csharp
var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
foreach (var file in provider.Files)
{
    if (!seen.Add(file.Key)) continue;  // 首次出现 (最高 ReadOrder) 为权威版本
    // ... export
}
```

**优势**：
- ✅ 从根源修复，一次遍历，零重复写入
- ✅ 所有场景自动生效（不限于 ConfigDB）
- ✅ 无需 Resource Patch Overlay 二次提取
- ✅ 性能提升：跳过重复文件的 Read() + WriteAllBytes()

### 3.3 Audio Pipeline

基于 `PlotAudio.json` 的发现，语音调用链路如下：

1. **OCR Trigger**: 识别到英文文本，检索得到 TextKey
2. **Name Derivation**: 根据规则推导语音文件名 `vo_` + `TextKey`
3. **Hash Calculation**: 使用 **FNV-1a (32-bit)** 算法计算哈希值
4. **Local Lookup**: 在本地查找 `{hash}.wem` 并转码播放

### 3.4 Font Pipeline

* **Source**: `Client/Content/Aki/UI/Framework/LGUI/Font/*.ufont`
* **Output**: `data/Fonts/*.ttf`（自动转换扩展名）
* **Usage**: UI 字体选择菜单自动加载

### 3.5 Database Schema

```json
{
  "normalized_key": {
    "key": "normalized_key",
    "matches": [
      {
        "text_key": "Main_LahaiRoi_3_1_1_2",
        "official_cn": "站住！",
        "source_json": "MultiText.json",
        "audio_rule": "vo_{text_key}"
      }
    ]
  }
}
```

### 3.6 Database Construction Pipeline

**Architecture**: `build_text_db_from_root_all()` 采用多根扫描策略。

#### 扫描根 (Scan Roots)

```python
roots = [
    data_root / "ConfigDB",                          # Primary ConfigDB
    data_root / "Client" / "Content" / "Aki" / "ConfigDB",
    data_root / "TextMap",
    data_root / "Client" / "Content" / "Aki" / "TextMap",
]
```

#### 嵌套目录自动发现 (2026-02-10 Enhancement)

**问题背景**：PAK 解包后可能产生嵌套结构（如 `ConfigDB/ConfigDB/`），导致补充数据库遗漏。

**解决方案**：递归扫描种子根的直接子目录，自动发现并加入包含语言对的子目录：

```python
for seed_root in seed_roots:
    roots.append(seed_root)  # 添加种子本身
    
    # 扫描直接子目录
    for child in seed_root.iterdir():
        if not child.is_dir():
            continue
        # 跳过语言目录本身（en, zh-Hans 等）
        if child.name in LANGUAGE_DIR_NAMES:
            continue
        # 检查子目录是否包含语言对
        for (en_name, zh_name) in langs:
            if (child / en_name).is_dir() and (child / zh_name).is_dir():
                roots.append(child)  # 发现嵌套语言目录，加入扫描
                break
```

#### 文件对扫描

对每个有效根执行：

```python
def scan_pair(en_dir: Path, zh_dir: Path):
    for ext in ("*.json", "*.db"):
        for en_path in en_dir.rglob(ext):
            rel = en_path.relative_to(en_dir)
            zh_path = zh_dir / rel
            if zh_path.exists():
                # 构建并合并数据库
                partial = build_text_db(en_path, zh_path)
                merge(partial, global_db)
```

#### 规范化键生成

```python
def normalize_en(text: str) -> str:
    """移除所有非字母数字字符，转小写"""
    return "".join(ch.lower() for ch in text if ch.isalnum())
```

**示例**：
- EN: `"Head to the Bioprinter and find the Kronablight"`
- Normalized: `"headtothebioprinterandfindthekronablight"` (40 chars)

#### 技术要点

| 特性 | 实现细节 |
|------|---------|
| **双键索引** | 每个条目生成 `key_en` 和 `key_zh` 两个索引键 |
| **去重合并** | 多个源文件中的同 text_key 条目自动合并 `matches[]` |
| **空值跳过** | EN/ZH 均为空的条目不纳入索引 |
| **数据库统计** | v3.1: **308,129 keys**, 262 MB JSON |

---

## 4. UI/UX Design

目标：让用户感觉这个浮窗是游戏自带的 UI，而不是第三方软件。

* **Design Language**: "Industrial Sci-Fi" (工业科幻)
* **Color Palette**:
  * Background: Semi-transparent Deep Black/Grey (`#1A1A1A` with 80% opacity)
  * Accent: Subtle gold (`#c9a64a`)
  * Text: White for CN, Light Grey for EN source
* **Typography**: 支持游戏原生字体（自动提取）
* **Interactions**:
  * 进度条 + 播放/暂停按钮
  * 热键截图
  * 菜单自定义

---

## 5. Directory Structure

```
Ludiglot/
├── config/             # Runtime configuration files (settings.json, etc.)
├── data/               # Application data (OcrData, Fonts, etc.) - often gitignored
├── docs/               # Documentation
├── log/                # Runtime logs
├── src/                # Source code
│   └── ludiglot/
│       ├── adapters/   # Game-specific logic (e.g., Wuthering Waves audio strategies)
│       ├── core/       # Core business logic and shared services
│       │   ├── audio/  # Audio processing (AudioResolver, etc.)
│       │   ├── ocr.py  # OCR engine wrappers
│       │   └── ...
│       ├── ui/         # GUI implementation (PyQt6)
│       └── __main__.py # Application entry point (CLI & GUI launcher)
├── tools/              # Dev scripts, debug tools, and one-off utilities
└── tests/              # Unit and integration tests (pytest)
```

---

## 6. Development & Architecture Guidelines

### 6.1 Architectural Layers

To maintain maintainability and testability, the code is organized into logical layers.

#### Layer 1: UI Layer (`src/ludiglot/ui/`)
*   **Responsibility**: Rendering the interface, handling user input, and displaying data.
*   **Guideline**: **NO complex business logic**. Use services or core modules to perform actual work.
*   **Example**: The `OverlayWindow` should capture a hotkey, then call `AudioResolver.resolve(...)`, not implement the resolution algorithm itself.

#### Layer 2: Core/Service Layer (`src/ludiglot/core/`)
*   **Responsibility**: heavy lifting of the application. Contains the "Single Source of Truth" for business rules (e.g., Audio Matching, Text Alignment, OCR pipelines).
*   **Guideline**: Code here must be decoupled from PyQt (where possible) so it can be used by CLI tools.
*   **Key Components**:
    *   `ludiglot.core.voice_map`: Mapping text keys to voice events.
    *   `ludiglot.core.audio_resolver`: Handling audio file resolution, checking cache, and handling gender fallback logic.

#### Layer 3: Adapter/Data Layer (`src/ludiglot/adapters/`)
*   **Responsibility**: Handling game-specific quirks (e.g., Wuthering Waves' specific naming conventions or hashing algorithms).

### 6.2 Logic Placement (The DRY Rule)
*   **Dev Scripts**: Any script intended for debugging, quick testing, or data investigation **MUST** be placed in the `tools/` directory.
    *   ❌ Do NOT create `.py` files in the project root.
    *   ✅ Create `tools/debug_my_feature.py`.
*   **Shared Logic**: If a piece of logic (e.g., "Find audio for this text") is needed by both the GUI and a CLI debug tool:
    1.  It **MUST** reside in `src/ludiglot/core/`.
    2.  It **MUST NOT** reside in `src/ludiglot/ui/` or `src/ludiglot/__main__.py`.

---

## 7. Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| GUI | PyQt6 |
| OCR | PaddleOCR-VL (本地部署 API 服务, 推荐), Windows.Media.Ocr (系统内置, 极速低内存) |
| Search | RapidFuzz |
| Audio | vgmstream, PyQt6.QtMultimedia |
| Pak Extract | FModelCLI (CUE4Parse) |
| Wwise Parse | wwiser |
