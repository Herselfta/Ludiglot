关于音频播放的处理逻辑，这是整个项目中最硬核、也最考验“逆向工程”能力的环节。由于《鸣潮》使用了 **Wwise** 作为音频引擎，我们不能简单地通过文件名直接引用音频，必须通过一套完整的 **“Hash 映射与资源提取”** 链路来实现。

以下是音频播放模块的详细技术实现方案，分为 **准备阶段 (Setup)**、**构建阶段 (Build)** 和 **运行阶段 (Runtime)** 三层逻辑。

---

### 一、 核心原理：Wwise 的“黑盒”

在游戏客户端里，并没有 `Main_LahaiRoi_1_2.mp3` 这种文件。
Wwise 为了性能，将文件名转换成了 **32位整数 ID (Hash ID)**，并将音频编码为 `.wem` 格式，通常打包在 `.pck` (Package) 文件中。

我们的核心任务是打通这条路：


---

### 二、 阶段一：资源提取 (Setup / Extractor)

*这是在用户本地运行的一次性（或更新时）脚本，用于绕过版权问题。*

**目的**：从用户安装的游戏中提取语音，转码为通用格式，并按 Hash ID 命名存储。

1. **定位源文件**：
* 脚本需引导用户选择游戏安装目录。
* 目标文件通常位于：`...\Wuthering Waves\Wuthering Waves Game\Client\Saved\Resources\3.0.0\Lang_zh\Base\` 下的 `pakchunk13-WindowsNoEditor.pak`（中文语音包）。


2. **解包与转码 (Unpack & Convert)**：
* 统一使用 **`E:\Ludiglot\tools\FModel.exe`** 导出资源。
* 我们需要集成 **`vgmstream`** (CLI版本) 到工具箱中。
* **操作逻辑**：
1. 用 FModel 加载游戏目录与 AES Key，挂载 `pakchunk13-WindowsNoEditor.pak`。
2. 在 FModel 中筛选并导出 `.wem` 文件（Wwise 音频流）。
3. **关键步骤**：使用 `vgmstream` 直接转码为 `.ogg`。
4. **保留文件名**：导出的 `.wem` 文件名本身就是 Hash ID (例如 `48291032.wem`)。转码后保存为 `./assets/audio/48291032.ogg`。





> **结果**：你的工具目录下会有几万个以数字命名的 `.ogg` 文件。

---

### 三、 阶段二：逻辑映射 (The Logic Bridge)

*这是在你的 ETL 脚本中完成的，用于告诉前端“什么文本对应什么哈希”。*

基于我们之前的发现 (`PlotAudio.json`)，映射规则如下：

#### 1. 命名规则推导

大多数剧情语音遵循前缀规则：

* **TextKey**: `Main_LahaiRoi_3_1_1_2`
* **AudioEventName**: `vo_Main_LahaiRoi_3_1_1_2` (注意：通常需要转为**全小写**进行哈希计算，Wwise 默认不区分大小写)。
额外的好感语音等额外资源命名方式可能会有所不同，需参考 `PlotAudio.json` 中的 `FileName` 字段。请你参考之前你遍历后的发现。

#### 2. FNV-1a 哈希算法实现

这是 Wwise 及其通用的标准算法。你需要用 Python 实现它来计算文件名。

```python
def wwise_fnv_hash(text: str) -> str:
    """
    计算 Wwise 标准的 32-bit FNV-1a Hash。
    输入必须预先转为小写 ( .lower() )。
    """
    text_bytes = text.lower().encode('utf-8')
    
    # FNV-1a constants for 32-bit
    FNV_PRIME_32 = 16777619
    FNV_OFFSET_32 = 2166136261
    
    hash_val = FNV_OFFSET_32
    
    for byte in text_bytes:
        hash_val = hash_val ^ byte
        hash_val = (hash_val * FNV_PRIME_32) & 0xFFFFFFFF  # 强制限制在32位
        
    return str(hash_val)

# 测试案例
# 假设 text_key = "Main_LahaiRoi_3_1_1_2"
# event_name = "vo_main_lahairoi_3_1_1_2"
# output_filename = wwise_fnv_hash(event_name) + ".ogg"

```

#### 3. 数据库注入

在构建 `game_text_db.json` 时，直接算出这个 Hash 并存进去，减轻运行时的计算压力。

```json
{
  "stoprightthere": {
    "matches": [
      {
        "cn": "站住！",
        "text_key": "Main_LahaiRoi_3_1_1_2",
        "audio_hash": "84920193" // 预先算好的 ID
      }
    ]
  }
}

```

---

### 四、 阶段三：运行时播放 (Runtime Flow)

*这是用户点击“播放”按钮时发生的事情。*

1. **触发**：用户 OCR 识别出英文，UI 显示对应中文卡片。
2. **检查**：前端读取 JSON 中的 `audio_hash` ("84920193")。
3. **定位**：检查本地路径 `os.path.exists("./assets/audio/84920193.ogg")`。
* **存在** -> 显示高亮的“播放图标”。
* **不存在** -> 图标置灰或隐藏（说明这句话可能没有语音，或者是提取不完整）。


4. **播放**：
* 使用 `PyQt6.QtMultimedia.QMediaPlayer` 或 `pygame.mixer` 播放该 `.ogg` 文件。
* **高级功能**：因为是 `.ogg`，加载速度极快，可以实现点击即播，甚至支持自动播放。



---

### 五、 潜在坑点与解决方案 (Robustness)

1. **哈希碰撞/规则例外**：
* *问题*：并非所有语音都叫 `vo_TextKey`。有些可能是 `vo_npc_TextKey`。
* *解决*：依赖 `PlotAudio.json` 中的 `FileName` 字段。
* 如果 `PlotAudio.json` 有明确定义，优先使用它指定的名字计算 Hash。
* 如果没有，再回退到 `vo_ + TextKey` 的默认规则。




2. **SoundBank 限制**：
* *问题*：有时候 Wwise 不把语音放在 `.pck` 里，而是放在零散的 `.bnk` 索引里。
* *解决*：MVP 阶段先只处理主线 `.pck`。如果找不到文件，UI 只是不显示播放按钮，程序不应崩溃。


3. **大小写敏感性**：
* *必须强调*：Wwise 的 Hash 计算**几乎总是**针对小写字符串的。`vo_Main...` 和 `vo_main...` 算出来的 Hash 是完全不同的。写代码时务必 `.lower()`。

---

## 6. 当前实现补充（2026-01-21）

### 6.1 实际命中链路（Runtime）

1. **文本匹配**：OCR → 归一化 → RapidFuzz 匹配 TextKey。
2. **事件名候选**：
  - `PlotAudio.json` → event 名；
  - 规则衍生（`vo_`/`play_`/`toplayer` 等变体）；
  - **BNK/TXTP 事件索引**（反向索引）追加候选。
3. **优先 WEM 直连**：
  - ExternalSource/WEM 直接命中（剧情语音常见）。
4. **BNK → TXTP → WAV**：
  - 通过 `wwiser.pyz` 生成 TXTP；
  - `vgmstream` 转码为 WAV 并缓存。

### 6.2 关键改动与防护

- **WWiser 调用修正**：参数与日志输出已修复，失败可定位。
- **TXTP 为空/失败**：会记录详细日志，避免静默失败。
- **缓存一致性**：支持 hash 命名副本，提升缓存命中。
- **ExternalSource 路径推断**：自动寻找 `WwiseExternalSource`，提升剧情语音命中率。



### 总结：你的开发指令

当你让 Copilot 写这部分时，可以这样描述：

> "I need to implement the **Audio Pipeline**.
> 1. Create a utility class `WwiseHash`. It must implement the **FNV-1a 32-bit algorithm**.
> 2. It should take a string, convert it to lowercase bytes, hash it, and return the integer as a string.
> 3. In the ETL builder, looks for the `PlotAudio.json` file.
> 4. For each entry, take the `FileName` field (e.g., 'vo_Main_LahaiRoi...'), hash it using our utility, and store this Hash ID in our main database.
> 5. This Hash ID will later map to a physical `.ogg` file extracted by `vgmstream`."
> 
>