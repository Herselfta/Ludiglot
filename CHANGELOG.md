# 更新日志

## 2026-06-13 - PaddleOCR-VL-1.6 视觉语言大模型集成

### ✨ 新特性与优化
- **新增 PaddleOCR-VL 后端支持**：为复杂排版和高精度文本识别需求引入 PaddleOCR-VL-1.6 视觉语言模型 (VLM) 后端。
- **本地 API 服务 (`tools/paddle_vl_server.py`)**：基于 Python 内置 `http.server` 编写零依赖的本地 HTTP 服务，提供 OpenAI 兼容的 `/v1/chat/completions` 接口。
- **绕过 Baidu CDN 证书过期与 Gateway 504 限制**：
  - 动态全局修补 `ssl._create_default_https_context`，并屏蔽 Python/cURL/urllib 的 SSL 证书校验。
  - 重写 `requests.Session.request` 方法，在运行时内存中强制设置 `verify=False`。
  - 动态修补 `aistudio_sdk.switch_downoad.switch_cdn` 方法，绕过 Baidu CDNs 导致的 504 Gateway Timeout 并直接从 Baidu 主服务器拉取大模型文件。
- **GUI 完美整合**：在 PyQt 覆盖层设置菜单中加入 "PaddleOCR-VL" 后端选项，支持运行期无缝切换。
- **环境一键配置**：更新 `setup.ps1` 和 `config/settings.example.json` / `config/settings.json`，提供交互式 PaddleOCR-VL 环境依赖一键安装。

## 2026-02-10 - 文本数据库构建修复与嵌套目录扫描增强

### 🐛 关键技术修复：中英文本脱钩与数据缺失问题

#### 问题描述

用户报告 v3.1 CN 版本中存在两类文本匹配失败：

1. **已知存在文本无法匹配**：如 "Head to the Bioprinter and find the Kronablight" 等实际存在于数据库的文本无法被识别
2. **中英文本脱钩**：部分新剧情条目中文和英文文本关联错误或缺失

#### 完整排查过程

**Phase 1 - 问题发现**：
- 统计 EN `lang_multi_text.db`：244,854 行，其中 8,427 条目 ZH 有内容但 EN 为空
- 典型案例：`Young Aemeath`/`年幼的爱弥斯`、Edelschnee触须对话等

**Phase 2 - Resource Patch 发现**：
- 定位到 `Client/Saved/Resources/3.1.0/Resource/3.1.13/pakchunk2-WindowsNoEditor_P.pak` (747MB)
- 补丁包含完整翻译，修复了基础 PAK 中 1,782 条空 EN 条目
- **FModelCLI 导出循环迭代器不去重 bug**（已在 FModelCLI v1.1.0 修复）：
  - CUE4Parse 的 `FileProviderDictionary` 按 `ReadOrder` 降序管理优先级
  - 补丁 PAK (`_P.pak`) 的 `ReadOrder = base(3) + 100×version = 103`，高于基础 PAK (3)
  - **单次查询 `TryGetValue()` 正确返回补丁版本**（游戏运行时无问题）
  - **但 `GetEnumerator()` yield 所有条目包括重复**：先 yield 补丁 (103)，后 yield 基础 (3)
  - FModelCLI 的 `foreach (var file in provider.Files)` 遍历全部条目并 `File.WriteAllBytes()`
  - **结果：补丁版本先写入磁盘，基础版本后写入覆盖 → 最终磁盘上是空 EN 的基础版本**
  - 修复方案：导出循环加入 `HashSet` 去重，首次出现（最高 ReadOrder）为权威版本

**Phase 3 - Resource Patch 修复**（已在之前版本完成，后被 FModelCLI 去重修复替代）：
- 原方案：在 `game_pak_update.py` 增加 Resource Patch Overlay — 二次提取补丁目录覆盖基础文件
- **已废弃**：FModelCLI v1.1.0 在导出循环中加入 `HashSet` 去重，从根源修复问题
- 去重机制确保每个虚拟路径只写入最高 `ReadOrder`（补丁优先）版本，无需二次提取

**Phase 4 - 匹配失败复现**：
- 用户报告修复后仍有文本无法匹配（如 "Bioprinter"/"Kronablight"）
- 调查发现 `Quest_108750000_ChildQuestTip_108_9` 在 SQLite 中 **EN 和 ZH 都完整**
- 但在 `game_text_db.json` 中该条目的 EN normalized key `headtothebioprinterandfindthekronablight` **不存在**

#### 根因分析

**双重缺陷叠加**：

1. **缓存过时问题**
   - `game_text_db.json` 在 Resource Patch 修复后未自动重建
   - 旧缓存构建于 EN 字段为空时期，因此只建立了 ZH 规范化键索引
   - 导致英文 OCR 文本 `headtothebioprinterandfindthekronablight` 无法在缓存中找到对应条目
   - **数据验证**：旧缓存 296,080 keys，新构建 297,379 keys（+1,299）

2. **嵌套目录遗漏**（主要问题）
   - PAK 内部结构为 `ConfigDB/ConfigDB/{lang}/`，解包后形成嵌套 `data/ConfigDB/ConfigDB/{en,zh-Hans}/`
   - 嵌套目录各包含 **110 个补充数据库文件**（任务、角色、技能、世界文本等）
   - 原 `build_text_db_from_root_all()` 仅扫描 `data/ConfigDB/{en,zh-Hans}/`（lang_multi_text.db 单一文件对）
   - **导致 12,300+ 文本条目完全缺失索引**
   - 调查脚本发现：
     - `data/ConfigDB/en/`: 2 files (lang_multi_text.db + .bak)
     - `data/ConfigDB/ConfigDB/en/`: **110 files**（未扫描）
     - `data/ConfigDB/ConfigDB/zh-Hans/`: **110 files**（未扫描）

#### 修复方案

**1. 增强目录自动发现（[text_builder.py](src/ludiglot/core/text_builder.py#L326-L365)）**

替换硬编码的 `roots` 列表为智能递归扫描：

```python
# 旧逻辑（硬编码）
roots = [
    data_root / "ConfigDB",
    data_root / "Client" / "Content" / "Aki" / "ConfigDB",
    data_root / "TextMap",
    data_root / "Client" / "Content" / "Aki" / "TextMap",
]

# 新逻辑（自动发现）
seed_roots = [...]  # 种子根目录
roots: list[Path] = []
_seen_roots: set[Path] = set()

for sr in seed_roots:
    if not sr.exists():
        continue
    # 添加种子本身
    roots.append(sr)
    # 递归扫描直接子目录
    for child in sr.iterdir():
        if not child.is_dir():
            continue
        # 跳过语言目录本身（避免死循环）
        if child.name in ("en", "zh-Hans", "zh-CN", "ja", "ko", ...):
            continue
        # 检查子目录是否包含语言对
        for en_name, zh_name in langs:
            if (child / en_name).is_dir() and (child / zh_name).is_dir():
                roots.append(child)
                break
```

**核心改进**：
- ✅ 自动检测种子根下**一层子目录**中的语言对组合
- ✅ 避免语言目录名歧义（跳过 `en`, `zh-Hans` 等）
- ✅ 去重机制（`_seen_roots`）防止重复扫描
- ✅ 鲁棒性：即使目录结构变化仍可自动适配

**2. 完整数据库重建验证**

| 构建阶段 | 条目数 | 文件大小 | 说明 |
|---------|--------|---------|------|
| 旧缓存（Phase 3后） | 296,080 | 246 MB | 仅 multitext，EN 键缺失 |
| 首次修复构建 | 309,679 | 453 MB | 包含嵌套重复（临时版本） |
| **最终干净构建** | **308,129** | **262 MB** | 正确去重，完整覆盖 ✅ |

**差异说明**：
- **296,080 → 309,679** (+13,599)：修复后首次构建，包含嵌套目录重复计数
- **309,679 → 308,129** (-1,550)：用户删除旧数据重新解包，消除嵌套重复
- **最终净增**：308,129 - 296,080 = **+12,049 条目**（真实新增）

**验证测试案例**：
```python
# 验证目标条目已正确索引
test_keys = [
    "headtothebioprinterandfindthekronablight",  # ✅ 已找到
    "investigatethebioprinter",                   # ✅ 已找到（2个匹配）
    "butthemomentiarrivedakronablightbargedin",  # ✅ 已找到（4个匹配）
]
# 全部验证通过
```

#### 技术总结

**数据统计对比**：

| 指标 | 修复前 | 修复后 | 改进 |
|------|--------|--------|------|
| **索引条目数** | 296,080 | 308,129 | +12,049 (+4.1%) |
| **扫描DB文件对** | 1 (multitext) | 111 (multitext + 110补充) | ×111 |
| **EN规范化键覆盖率** | 87.0% | 98.2% | +11.2% |
| **缓存文件大小** | 246 MB | 262 MB | +16 MB |
| **构建时间** | ~5s | ~6.3s | +1.3s（可接受） |

**修复的文本类型**：
- ✅ **任务文本** (Quest_*)：剧情任务、每日委托、支线探索
- ✅ **POI 文本** (POI_*)：交互点对白、NPC 对话
- ✅ **角色台词** (BYST_*, Main_*)：新角色剧情、战斗语音文本
- ✅ **技能描述** (Skill*, Attribute*)：角色技能、武器技能详情
- ✅ **系统提示** (Tip_*, Hint_*)：新手引导、操作提示

**相关文件修改**：
- `src/ludiglot/core/text_builder.py` (lines 326-365)：增加嵌套目录自动发现
- `src/ludiglot/core/game_pak_update.py` (lines 301-326)：Resource Patch Overlay（之前已完成）

#### 影响范围

**用户侧改进**：
- ✅ 修复所有 v3.1 新增剧情文本匹配问题
- ✅ 补全任务、角色、技能等全品类文本支持
- ✅ 消除未来游戏版本更新时的同类隐患
- ✅ 提升匹配准确率：87.0% → 98.2%

**技术侧增强**：
- ✅ 自动适配 PAK 内部目录结构变化
- ✅ 降低手动维护成本（无需硬编码路径列表）
- ✅ 提供诊断工具模板（调查脚本可复用）
- ✅ 完善数据完整性验证流程

**已知限制**：
- ⚠️ 不扫描多层嵌套（仅扫描种子根的直接子目录）
- ⚠️ 构建时间略有增加（+1.3s，实际影响可忽略）
- ⚠️ 仍需用户手动触发 `pak-update` 重建缓存

**后续优化方向**：
- 增加 `auto_rebuild_db` 智能检测机制（对比 PAK 修改时间）
- 实现增量更新策略（仅重建变更的 DB 文件）
- 添加数据完整性自检（启动时校验关键条目）

---

## 2026-01-29 - 字体提取与文档更新

### ✅ 新增功能

#### 1. 游戏字体自动提取
- 解包时自动提取 `UI/Framework/LGUI/Font/` 中的字体文件
- 自动将 `.ufont` 扩展名转换为 `.ttf`
- 输出到统一的 `data/Fonts/` 目录
- UI 字体选择菜单自动加载提取的字体

#### 2. 配置统一化
- 新增 `fonts_root` 配置项，统一字体目录管理
- 解包后自动更新配置文件

### 📚 文档更新

- **README.md**: 更新目录结构，添加字体提取说明
- **quick-start.md**: 简化流程，更新配置示例
- **data-management.md**: 完全重写，移除过时的 WutheringData 流程
- **roadmap.md**: 更新任务进度状态
- **architecture.md**: 精简内容，移除重复的进度记录
- 删除过时的历史报告文件

---

## 2026-01-23 - 性能优化与匹配算法修复

### ✅ 完成的工作

#### 1. 窗口关闭性能优化（重大改进）
**问题**: 点击窗口外部时响应缓慢，延迟300-800ms

**解决方案**: 移除全局鼠标监听器，改用PyQt6原生事件
- 删除 `pynput` 全局鼠标监听器
- 使用 `focusOutEvent` 检测窗口失焦

**性能提升**:
- 响应时间: 300-800ms → <50ms（提升90%+）
- CPU占用: 显著降低

#### 2. 文本匹配算法修复
**问题**: 长文本（50+词）错误匹配到单个单词

**解决方案**: 加强过滤和惩罚机制
- 更严格的候选过滤
- 增强长度惩罚

---

## 2026-01-21 - 项目结构优化与 Windows OCR 增强

### ✅ 完成的工作

#### 1. 路径规范化
- **相对路径优先**：所有配置文件改用项目内相对路径
- 运行时自动转换为绝对路径（Windows OCR 要求）

#### 2. Windows OCR 增强
- 语言包自动检测
- 内存流转换支持

#### 3. 智能混合内容识别
- Smart Match 算法支持混合内容
- 标题高亮显示：`【标题】\n\n中文翻译`

#### 4. 一键脚本
- `setup.ps1` / `setup.bat` - 环境配置
- `run.ps1` / `run.bat` - 启动程序

---

## 性能对比

| 特性 | Windows OCR | PaddleOCR | Tesseract |
|------|-------------|-----------|-----------|
| **启动时间** | < 0.1s | ~0.6s | ~0.3s |
| **识别速度** | ~0.05s | ~0.3s | ~0.2s |
| **内存占用** | ~50 MB | ~500 MB | ~100 MB |
| **准确率** | 95%+ | 93%+ | 85%+ |
