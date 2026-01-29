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
* **Vision**: OCR 引擎（Windows OCR 优先，PaddleOCR/Tesseract 回退）。
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

### 3.2 Audio Pipeline

基于 `PlotAudio.json` 的发现，语音调用链路如下：

1. **OCR Trigger**: 识别到英文文本，检索得到 TextKey
2. **Name Derivation**: 根据规则推导语音文件名 `vo_` + `TextKey`
3. **Hash Calculation**: 使用 **FNV-1a (32-bit)** 算法计算哈希值
4. **Local Lookup**: 在本地查找 `{hash}.wem` 并转码播放

### 3.3 Font Pipeline

* **Source**: `Client/Content/Aki/UI/Framework/LGUI/Font/*.ufont`
* **Output**: `data/Fonts/*.ttf`（自动转换扩展名）
* **Usage**: UI 字体选择菜单自动加载

### 3.4 Database Schema

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
| OCR | Windows.Media.Ocr (primary), PaddleOCR, Tesseract |
| Search | RapidFuzz |
| Audio | vgmstream, PyQt6.QtMultimedia |
| Pak Extract | FModelCLI (CUE4Parse) |
| Wwise Parse | wwiser |
