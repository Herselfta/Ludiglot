# Project Manifest: Ludiglot

**Architecture:** Modular Core + Game Adapter
**Target:** Immersive Language Learning Tool for Wuthering Waves

## 1. Project Vision & Philosophy

我们要构建一个**非侵入式、原生体验**的语言学习引擎。它不仅仅是一个翻译器，而是一个“游戏伴侣”，能够让玩家在不脱离游戏沉浸感的前提下，通过 OCR 逆向检索官方文本和语音，实现母语级的剧情理解。

### Core Principles

1. **Safe & External**: 坚持使用 OCR 和外部数据库，严禁内存读写（Anti-Cheat Compliance）。
2. **Native Fidelity**:
* **Text**: 必须显示官方汉化文本，拒绝机翻。
* **Audio**: 必须能够播放对应的官方语音。
* **Visual**: UI 必须复刻《鸣潮》原生科技风（Tacet Mark 风格），与游戏界面无缝融合。


3. **Automated**: 数据源自动追踪上游开源仓库，实现“零维护”更新。

## 2. System Architecture (Micro-Kernel)

系统采用 **Core (通用内核)** + **Adapter (游戏适配器)** 模式。

### Module A: The Core (GlotGame Engine)

*通用组件，不包含特定游戏逻辑。*

* **Infrastructure**: Git 自动同步管理器。
* **Vision**: `PaddleOCR` 封装（支持 GPU/CPU 自动切换）。
* **Search**: `RapidFuzz` 模糊匹配引擎。
* **UI**: 基于 `PyQt6` 的覆盖层系统，支持 QSS 样式表定制。

### Module B: The Adapter (`adapters/wuthering_waves`)

*《鸣潮》特化逻辑。*

* **Data Mapper**: 定义如何解析 `Dimbreath/WutheringData`。
* **Audio Strategy**: 实现 `vo_` 前缀 + Wwise Hash 计算逻辑。
* **Asset Extractor**: 用户本地运行的脚本，用于解包/转换语音文件。

## 3. Data Engineering & Logic (The Brain)

### 3.1 Text Pipeline (TextMap)

* **Source**: `TextMap/en/MultiText.json` & `zh-Hans/...`
* **Logic**:
* 建立映射：`TextKey (Main_LahaiRoi_3_1_1_2)`  `Chinese Text`。
* 建立索引：`Normalized English (stoprightthere)`  `TextKey`。
* **Composite Key**: 防止 ID 碰撞，使用 `{RelativePath}::{TextKey}` 作为唯一标识。



### 3.2 Audio Pipeline (The "Rosetta Stone" Discovery)

基于 `PlotAudio.json` 的发现，语音调用链路如下：

1. **OCR Trigger**: 识别到英文文本，检索得到 TextKey (`Main_LahaiRoi_3_1_1_2`).
2. **Name Derivation**: 根据 `PlotAudio.json` 规则，推导语音文件名为 `vo_` + `TextKey`.
3. **Hash Calculation**: 使用 **FNV-1a (32-bit)** 算法计算字符串 `"vo_Main_LahaiRoi_3_1_1_2"` 的哈希值（例如 `123456789`）。
4. **Local Lookup**: 在本地缓存目录查找 `123456789.wem` (或转码后的 `.ogg`)。

### 3.3 Database Schema (Target Output)

```json
// game_text_db.json
{
  "stoprightthere": {
    "key": "stoprightthere",
    "matches": [
      {
        "text_key": "Main_LahaiRoi_3_1_1_2",
        "official_cn": "站住！",
        "source_json": "MultiText_1sthalf.json",
        "audio_rule": "vo_{text_key}", // Adapter tells Core how to find audio
        "terms": ["Rover"] // Highlight keywords
      }
    ]
  }
}

```

## 4. UI/UX Design (New Task: Native Style)

目标：让用户感觉这个浮窗是游戏自带的 UI，而不是第三方软件。

* **Design Language**: "Industrial Sci-Fi" (工业科幻) / "Post-Apocalyptic Clean" (废土极简)。
* **Color Palette**:
* Background: Semi-transparent Deep Black/Grey (`#1A1A1A` with 80% opacity).
* Accent: Wuthering Cyan (`#3EE5E5` - 类似于声骸/频率的颜色).
* Text: White (`#FFFFFF`) for CN, Light Grey (`#CCCCCC`) for EN source.


* **Typography**: 使用无衬线字体（类似 *HarmonyOS Sans* 或 *Roboto*），字重偏细。
* **Animations**: 窗口出现时带有轻微的“故障干扰 (Glitch)”或“频率展开”动画。
* **Interactions**:
* **Play Button**: 一个简单的波形图标，点击播放语音。
* **Expand/Collapse**: 极简的箭头。



## 5. Development Roadmap (Checklist)

### Phase 0: Infrastructure

* [ ] **Task 0.1**: Implement `GitManager` (Auto-pull `WutheringData`).
* [ ] **Task 0.2**: Verify `vgmstream` CLI works on local machine.

### Phase 1: Data Engineering (The Hard Part)

* [ ] **Task 1.1**: Write Schema Analyzer (Explore JSON structures).
* [ ] **Task 1.2**: Implement **Text Builder** (Parse `MultiText` -> DB).
* [ ] **Task 1.3**: Implement **Audio Mapper** (Parse `PlotAudio.json` -> logic).
* [ ] **Task 1.4**: Write `AudioHashCalculator` (FNV-1a implementation).

### Phase 2: Core Logic

* [ ] **Task 2.1**: PaddleOCR Integration.
* [ ] **Task 2.2**: Fuzzy Search Logic.
* [ ] **Task 2.3**: Audio Player Integration (`PyQt6.QtMultimedia`).

### Phase 3: GUI Implementation (Native Style)

* [ ] **Task 3.1**: Create `OverlayWindow` class (Frameless, Always-on-top).
* [ ] **Task 3.2**: Write `style.qss` (The Wuthering Waves Theme).
* Define borders, backgrounds, and font styles.


* [ ] **Task 3.3**: Implement "Glitch" entrance animation.

---

## 6. 当前进度摘要（2026-01-24）

### 本次更新（UI菜单与截图功能修复）

#### 待修复的已知问题

1. **菜单UI显示问题**
   - ❌ **子菜单箭头隐藏失败**：用户需要隐藏子菜单（如"Font Settings"、"Size"等）右侧的展开三角箭头，但当前CSS规则未生效
     - 已尝试：`QMenu::right-arrow { image: none; width: 0px; }`
     - 状态：三角箭头仍然显示
   
   - ❌ **Weight勾选标记位置反向**：当前逻辑与预期相反
     - 期望：菜单向左展开时勾选标记在左侧，向右展开时在右侧
     - 实际：位置反了
     - 当前代码：
       ```css
       QMenu[layoutDirection="RightToLeft"]::indicator { margin-right: 6px; }  /* 应该是margin-left */
       QMenu[layoutDirection="LeftToRight"]::indicator { margin-left: 6px; }   /* 应该是margin-right */
       ```

2. **SpinBox箭头显示异常**
   - ❌ **增减按钮显示为矩形**：上下箭头应该是三角形，但显示为完全相同的矩形
     - 已尝试方案：
       1. SVG data URI（未显示）
       2. CSS border三角形（显示为矩形）
       3. Unicode字符▲▼（未应用）
     - 问题根源：Qt StyleSheet的`::up-arrow`和`::down-arrow`伪元素渲染问题
     - 状态：需要重新设计解决方案

3. **OCR截图功能崩溃**
   - ❌ **Alt+W触发后程序卡住**：
     - 日志显示：`[ScreenSelector] 背景Pixmap尺寸...` 后无后续输出
     - 根本原因：`QEventLoop`未导入，导致`NameError`
     - 已修复：添加`from PyQt6.QtCore import QEventLoop`到导入列表
     - 状态：导入已修复，但仍需实际测试验证功能

4. **字体大小警告持续**
   - ⚠️ **Qt警告频繁出现**：`QFont::setPointSize: Point size <= 0 (-1), must be greater than 0`
     - 原因：某些情况下`self.current_font_size`可能为负数或None
     - 已修复：增强验证逻辑
       ```python
       try:
           size_val = int(self.current_font_size) if self.current_font_size else 13
       except (ValueError, TypeError):
           size_val = 13
       valid_size = max(8, min(72, size_val))
       ```
     - 状态：需要验证是否还有其他触发路径

#### 技术诊断

- **日志系统升级**：已实现Qt消息处理器捕获，所有Qt警告现在都会写入`log/gui.log`
  ```python
  from PyQt6.QtCore import qInstallMessageHandler
  qInstallMessageHandler(qt_message_handler)
  ```

- **ScreenSelector健壮性**：增强异常处理
  ```python
  def get_region(self) -> QRect | None:
      try:
          loop = QEventLoop()
          # ... 正常流程
      except Exception as e:
          print(f"[ScreenSelector ERROR] {e}")
          traceback.print_exc()
          return None
  ```

#### 下一步行动计划

1. **修复子菜单箭头隐藏**：
   - 尝试在`setStyleSheet`中添加`QMenu::indicator { width: 0; }`来真正隐藏
   - 或使用`QMenu`的`setTearOffEnabled(False)`相关属性

2. **修正Weight指示标方向**：交换margin-left/right的配置

3. **解决SpinBox箭头**：
   - 方案A：使用QProxyStyle重写绘制逻辑
   - 方案B：完全放弃CSS，使用自定义widget替代QSpinBox
   - 方案C：接受系统默认样式（最简单）

4. **验证截图功能**：运行实际测试确认Alt+W快捷键工作

---

## 6.1 历史进度（2026-01-23）

### 本次更新（GUI/匹配/交互稳定性）

- ✅ 点击窗口外自动隐藏，状态同步修复
  - 新增全局鼠标监听（程序可见时启用、隐藏时关闭），捕获到窗口外点击后立即隐藏窗口
  - 统一使用 `isHidden()` 判断显隐状态，快捷键 Alt+H 不再需要按两次
  - 相关日志：`[WINDOW] 捕获到窗口外点击 (x,y)，隐藏窗口`

- ✅ 标题翻译（混合模式：标题 + 正文）
  - 对识别出的标题（如“Lynae”）单独查询 DB，优先显示中文名（如“琳奈”）
  - 展示样式：`【中文标题】\n\n中文正文`

- ✅ 部分截屏的长文本匹配优化（Containment-first）
  - `_search_db` 前缀/包含匹配强化：降低触发阈值（12→10），放宽长度差（+2000），包含命中评分提升到 0.98，先于模糊匹配
  - 混合模式额外“包含校验”：若拼接后的正文 key 未被 best 命中包含，则改用包含该 key 的最短 DB 键，避免被“长度相近但不相关”的条目误吸引

- ✅ GUI易读性与控件整合
  - 原文 `#SourceText`：字体提升至 14pt、字重 600，颜色调高到 `#cbd5e1`，指定中文宋体系列以提升可读性
  - 移除旧的 Play/Stop 按钮；播放控制统一为进度条左侧单一“播放/暂停”按钮
  - 播放/暂停按钮使用系统标准图标（QStyle），避免彩色 emoji
  - 音频进度条 + 拖动跳转 + 时间标签；定时刷新（100ms）

- ✅ 音频缓存路径规范
  - 将 `audio_cache_path`、`audio_cache_index_path`、`audio_txtp_cache` 统一为项目内相对路径：`cache/audio`、`cache/audio/audio_index.json`、`cache/audio/txtp`
  - 配置解析自动转换为绝对路径（不再在工程外生成缓存）

### 已知限制与后续打算

- 音频结束状态同步：当前使用 QTimer 轮询进度；后续可在非阻塞播放模式下连接 `QMediaPlayer.mediaStatusChanged`，在 `EndOfMedia` 时自动复位 UI（停止计时器、还原按钮图标）
- 匹配模型后续增强：
  - 引入 `top_k` 候选，在 `_lookup_best` 中结合角色/标题上下文二次筛选
  - 对超长文本采用 token containment 打分，降低顺序差异的影响
  - 标题（角色名）作为上下文过滤器，提高跨角色同名技能时的命中精度

---

## 6.1 历史进度（2026-01-21）

### 最新完成（本次更新）

- **✅ Windows 原生 OCR 集成**：实现并优先调用 Windows.Media.Ocr API
  - 优先级策略：Windows OCR → PaddleOCR → Tesseract
  - 自动依赖检测和详细错误提示
  - 完整的 WinRT 依赖管理（6个模块）
  - 修复边界框解析（从 words 聚合 bounding_rect）
  - 性能优异：启动 < 0.1s，识别 ~0.05s，内存 ~50 MB

- **✅ OCR 日志增强**：实时显示后端选择、失败原因和回退路径
  - 初始化日志：语言包状态、依赖检查
  - 识别日志：实际使用的后端、识别行数
  - 错误日志：详细的异常类型和解决建议

- **✅ 综合测试验证**：创建测试脚本和测试图片
  - `tools/test_windows_ocr.py`：Windows OCR 独立测试
  - `tools/test_ocr_comprehensive.py`：多场景综合测试
  - `tools/debug_match_capture.py`：完整流程回归测试

- **✅ 文档更新**：
  - 新增 `PrivateDevDoc/WindowsOCR.md` 完整说明文档
  - 更新 `pyproject.toml` 添加 WinRT 依赖

### 已完成/实现（之前）

- **OCR 多后端**：PaddleOCR + Tesseract 兜底，并新增 **Windows 原生 OCR**（WinSDK/WinRT）优先路径。
- **OCR 日志增强**：日志输出实际使用的后端（Windows/Tesseract/Paddle），并显式提示 Windows OCR 不可用原因。
- **截图鲁棒性**：过小选区（如 1x1）会直接跳过，避免 `axes don't match array` 异常。
- **文本匹配鲁棒性**：
  - 列表/短行识别更稳定，避免“多行只命中一个”。
  - 长文本场景抑制“单词级误命中”。
  - 加入前缀/包含匹配与长度惩罚，降低短条目误中长文本。
- **音频索引与检索**：
  - 事件名索引（BNK/TXTP 反向索引）提升命中率。
  - ExternalSource/WEM 直接命中（剧情语音常见）。
  - WWiser 调用与日志捕获修正，TXTP 生成失败可定位。
- **调试脚本**：新增基于 `capture.png` 的 OCR + 匹配回归脚本。

### 当前已知限制

- **Windows OCR 运行时**：WinRT 依赖在部分环境中不可用，自动回退到 Tesseract/Paddle。
- **黄色字体识别**：PaddleOCR 对黄字命中仍不稳定，Windows OCR 是首选但依赖运行时。

### 最近样例验证（自动化）

- 使用 `capture.png` 进行 OCR + 匹配回归测试。
- 日志记录实际后端与匹配结果，保证可追踪。

---

## 7. 数据源与路径管理（重要）

### 用户需要准备的数据

#### 1. 游戏文本数据（必需）
- **来源**：[Dimbreath/WutheringData](https://github.com/Dimbreath/WutheringData)
- **建议位置**：data/WutheringData/
- **获取方式**：
  ```bash
  cd data
  git clone https://github.com/Dimbreath/WutheringData.git
  ```
- **所需文件**：
  - TextMap/en/MultiText.json
  - TextMap/zh-Hans/MultiText.json
- **更新方式**：cd data/WutheringData && git pull

#### 2. 游戏音频资源（可选）
- **来源**：使用 FModel 从游戏目录提取
- **AES 密钥**：参考 [ClostroOffi/wuwa-aes-archive](https://github.com/ClostroOffi/wuwa-aes-archive)
- **建议位置**：data/FModelExports/
- **所需文件**：
  - .wem 文件（音频）→ Client/Content/Aki/WwiseAudio_Generated/Media/zh/
  - .bnk 文件（事件映射）→ Client/Content/Aki/WwiseAudio_Generated/Event/zh/

### 路径规范

#### 配置文件中的路径（相对路径）
```json
{
  "data_root": "data/WutheringData",
  "audio_cache_path": "cache/audio",
  "audio_wem_root": "data/FModelExports/.../Media/zh"
}
```

#### 运行时处理（自动转换为绝对路径）
- **Windows OCR 要求**：必须使用绝对路径（如 C:\Users\...\img.jpg）
- **自动处理**：代码会自动将相对路径转换为绝对路径
- **用户无需关心**：配置文件中只需使用相对路径即可

#### 语言包依赖（Windows OCR）
- **要求**：Windows 系统必须安装对应语言包
  - 识别英文：需要"英语"语言包
  - 识别中文：需要"中文(简体)"语言包
- **检查方式**：Settings → Time & Language → Language
- **启动检测**：程序启动时会自动检测并提示

### Ludiglot 的职责

1. **构建索引**：从 WutheringData 构建搜索数据库（cache/game_text_db.json）
2. **转换音频**：使用 vgmstream 将 .wem 转为 .wav/.ogg
3. **缓存管理**：在 cache/audio/ 管理转换后的音频
4. **不追踪用户数据**：所有 data/, cache/ 目录在 .gitignore 中排除

---

## 8. 最新更新（2026-01-21）

### ✅ 智能混合内容识别
- 创建 smart_match.py 模块，自动识别混合内容（标题 + 描述）
- 支持缩写处理（Ms., Dr., Mr. 等）
- 标题高亮显示：【标题】\n\n中文翻译

### ✅ 项目结构优化
- 所有路径改为项目内相对路径
- 完善 .gitignore，保护私有数据
- 添加 data/, cache/ 目录说明

### ✅ 一键脚本与文档
- 一键配置脚本：setup.ps1 / setup.bat
- 一键运行脚本：
un.ps1 / 
un.bat
- 现代化文档：README.md, CONTRIBUTING.md, LICENSE

### 🔄 待实现
- [ ] 内存流转换（避免硬盘读写）
- [ ] 语言包自动检查
- [ ] 废弃 Tesseract，PaddleOCR 改为可选


---

## 7. 数据源与路径管理（重要）
