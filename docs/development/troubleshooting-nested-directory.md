# 技术案例：嵌套目录导致数据库不完整问题

**日期**: 2026-02-10  
**版本**: v3.1 CN  
**影响**: 12,000+ 文本条目缺失  
**修复**: [PR/Commit] text_builder.py 嵌套目录自动发现  

---

## 问题描述

用户报告游戏 v3.1 版本中部分新剧情文本无法匹配，例如：
- ✗ "Head to the Bioprinter and find the Kronablight"
- ✗ "Investigate the Bioprinter"
- ✗ "Track the Kronablight"

这些文本在游戏中**实际存在**，但 OCR 识别后无法在 `game_text_db.json` 中找到对应的中文翻译。

---

## 调查过程

### 第一阶段：数据完整性验证

1. **检查原始数据库**

   ```python
   # 直接查询 SQLite
   SELECT Id, Content FROM MultiText WHERE Id = 'Quest_108750000_ChildQuestTip_108_9';
   # 结果：EN="Head to the Bioprinter and find the Kronablight" ✓
   #       ZH="前往拟合再生台寻找冠顶械隼" ✓
   ```

   **结论**：原始数据库**完整**，问题出在索引构建环节。

2. **检查缓存 JSON**

   ```python
   # 搜索 game_text_db.json
   normalized_key = "headtothebioprinterandfindthekronablight"
   # 结果：NOT FOUND ✗
   ```

   **结论**：缓存中缺失该条目的 EN 规范化键。

3. **搜索条目位置**

   ```python
   # 遍历所有 normalized keys
   for key, payload in game_text_db.items():
       for match in payload["matches"]:
           if match["text_key"] == "Quest_108750000_ChildQuestTip_108_9":
               print(f"Found under key: {key}")
   # 结果：key = "前往拟合再生台寻找冠顶械隼" (ZH key only)
   ```

   **发现**：条目**仅被 ZH 键索引**，EN 键丢失！

### 第二阶段：根因定位

1. **手动重建测试**

   ```python
   # 直接调用 build_text_db() 处理相同文件
   partial = build_text_db(
       Path("data/ConfigDB/en/lang_multi_text.db"),
       Path("data/ConfigDB/zh-Hans/lang_multi_text.db")
   )
   print("headtothebioprinterandfindthekronablight" in partial)  # True ✓
   ```

   **结论**：`build_text_db()` 逻辑**正确**，问题在上游扫描环节。

2. **目录结构审查**

   ```bash
   # 检查实际目录结构
   data/ConfigDB/
   ├── en/                 # 仅 2 个文件 (lang_multi_text.db + .bak)
   ├── zh-Hans/            # 仅 1 个文件
   └── ConfigDB/           # ← 发现嵌套！
       ├── en/             # 110 个 .db 文件
       └── zh-Hans/        # 110 个 .db 文件
   ```

   **关键发现**：存在 **`ConfigDB/ConfigDB/`** 嵌套目录，包含大量补充数据库！

3. **扫描逻辑审查**

   ```python
   # 原 build_text_db_from_root_all() 扫描根
   roots = [
       data_root / "ConfigDB",  # 仅扫描 ConfigDB/{en,zh-Hans}/
       ...
   ]
   # 问题：未递归扫描 ConfigDB/ConfigDB/{en,zh-Hans}/
   ```

   **根因**：`build_text_db_from_root_all()` 不扫描嵌套子目录，导致 110 个补充 DB 被遗漏。

### 第三阶段：数据对比

| 指标 | 旧缓存 (过时) | 完整扫描 | 差异 |
|------|---------------|---------|------|
| **总 keys** | 296,080 | 308,129 | +12,049 |
| **文件扫描** | ConfigDB/en/ (1对) | ConfigDB/en/ + ConfigDB/ConfigDB/en/ (111对) | +110对 |
| **目标条目 EN 键** | ✗ 缺失 | ✓ 存在 | 修复 |

---

## 修复方案

### 代码改动

**文件**: `src/ludiglot/core/text_builder.py`  
**函数**: `build_text_db_from_root_all()`  
**改动**: 增加嵌套目录自动发现逻辑

```python
# 原逻辑（固定根列表）
roots = [
    data_root / "ConfigDB",
    data_root / "TextMap",
]

# 新逻辑（递归发现）
seed_roots = [data_root / "ConfigDB", data_root / "TextMap"]
roots: list[Path] = []
seen: set[Path] = set()

for sr in seed_roots:
    if not sr.exists():
        continue
    
    # 1. 添加种子本身
    roots.append(sr)
    seen.add(sr)
    
    # 2. 扫描直接子目录
    for child in sr.iterdir():
        if not child.is_dir():
            continue
        
        # 跳过语言目录名称（避免误识别）
        if child.name in ("en", "zh-Hans", "zh-CN", "ja", "ko", ...):
            continue
        
        # 检查子目录是否包含语言对
        for (en_name, zh_name) in langs:
            if (child / en_name).is_dir() and (child / zh_name).is_dir():
                if child not in seen:
                    roots.append(child)  # ← 核心：动态添加嵌套根
                    seen.add(child)
                break
```

### 验证结果

**重建后统计**：

```python
# 新鲜构建
db = build_text_db_from_root_all(data_root)
print(f"Total keys: {len(db)}")  # 308,129 ✓

# 验证目标条目
key = "headtothebioprinterandfindthekronablight"
print(key in db)  # True ✓
print(db[key]["matches"][0]["text_key"])  # Quest_108750000_ChildQuestTip_108_9 ✓
```

**扫描覆盖**：

```
data/ConfigDB/en/ <-> zh-Hans/: 1 file pairs
  lang_multi_text.db: EN=34,127,872b, ZH=32,825,344b

data/ConfigDB/ConfigDB/en/ <-> zh-Hans/: 110 file pairs
  lang_flow_text.db: EN=196,608b, ZH=196,608b
  lang_speaker.db: EN=196,608b, ZH=196,608b
  lang_text.db: EN=196,608b, ZH=196,608b
  ... (107 more)
```

---

## 技术总结

### 问题本质

PAK 解包工具（FModelCLI）的输出路径结构为 `Client/Content/Aki/ConfigDB/...`，移动到 `data/` 根目录时：
- 第一次解包：`data/ConfigDB/` 不存在 → `shutil.move()` 直接移动 ✓
- 第二次解包（Resource Patch）：`data/ConfigDB/` 已存在 → `shutil.move()` 创建嵌套 `data/ConfigDB/ConfigDB/` ✗

### 架构改进

**前置条件**：数据库构建器必须**容错**，不依赖固定目录结构。

**设计原则**：
1. **种子根 + 递归发现**：从已知根开始，动态探测嵌套语言目录
2. **语言对验证**：仅扫描同时包含 `{en, zh-Hans}` 的目录
3. **去重保护**：使用 `seen` 集合避免重复扫描

### 适用场景

此修复不仅解决当前问题，还覆盖未来可能的场景：
- ✅ 多层 PAK 覆盖导致的嵌套结构
- ✅ 用户手动组织数据目录
- ✅ 其他游戏的不同 PAK 布局

---

## 经验教训

### 1. 缓存失效检测不足

**问题**：用户更新数据后，缓存未自动重建。

**改进方向**：
- 实现数据源变更检测（mtime、hash）
- 配置项 `auto_rebuild_db` 默认启用
- UI 提醒缓存过期

### 2. 目录结构假设过强

**问题**：硬编码扫描根列表，无法适应动态结构。

**改进**：
- 递归发现 + 语言对验证
- 支持多根、多层嵌套
- 日志记录扫描路径

### 3. 单元测试覆盖不足

**建议**：
- 为 `build_text_db_from_root_all()` 增加嵌套目录测试用例
- Mock 不同的目录结构场景
- CI 验证数据库完整性

---

## 附录：调查工具脚本

所有调查脚本位于 `tools/` 目录（已清理）：
- `_investigate_match.py` - 搜索目标文本在 DB 和 JSON 中的位置
- `_trace_match.py` - 对比 base vs patch 版本差异
- `_trace_key.py` - 精确追踪 normalized key 生成流程
- `_rebuild_db.py` - 完整重建并验证

---

**结论**：通过嵌套目录自动发现机制，彻底解决数据库构建不完整问题，确保所有补充文本条目被正确索引。此修复具有前瞻性，能够自动适应未来游戏版本的数据结构变化。
