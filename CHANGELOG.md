# 更新日志

## 2026-02-10 - 文本数据库构建修复与嵌套目录扫描增强

### 🐛 关键技术修复

#### 问题描述
用户报告 v3.1 CN 版本中部分新剧情文本无法匹配，例如 "Head to the Bioprinter and find the Kronablight" 等实际存在于数据库中的文本却无法被正确识别。

#### 根因分析

**双重缺陷叠加**：

1. **缓存过时问题**
   - `game_text_db.json` 在数据更新后未自动重建
   - 旧缓存中部分条目（如 `Quest_108750000_ChildQuestTip_108_9`）只有 ZH 规范化键，缺失 EN 规范化键
   - 导致英文 OCR 文本 `headtothebioprinterandfindthekronablight` 无法在缓存中找到对应条目

2. **嵌套目录遗漏**
   - PAK 解包后形成 `data/ConfigDB/ConfigDB/{en,zh-Hans}/` 嵌套结构（各110个DB文件）
   - 原 `build_text_db_from_root_all()` 仅扫描 `data/ConfigDB/{en,zh-Hans}/`（仅1个文件对）
   - **~110个补充数据库**（包括任务、角色、技能等文本）未被纳入索引
   - 导致 **12,300+ 文本条目缺失**

#### 修复方案

**1. 增强目录自动发现（[text_builder.py](src/ludiglot/core/text_builder.py#L326-L365)）**

```python
# 新增：自动发现嵌套语言目录对
for sr in seed_roots:
    if not sr.exists():
        continue
    # 添加种子本身
    roots.append(sr)
    # 递归扫描直接子目录，若包含语言对则加入扫描
    for child in sr.iterdir():
        if not child.is_dir():
            continue
        # 跳过语言目录本身
        if child.name in ("en", "zh-Hans", ...):
            continue
        # 检查子目录是否包含语言对
        for en_name, zh_name in langs:
            if (child / en_name).is_dir() and (child / zh_name).is_dir():
                roots.append(child)
                break
```

**2. 完整数据库重建**
- 重建后统计：**308,129 keys**（较旧版 296,080 +12,049）
- 文件大小：262 MB（干净版，无重复）
- 验证目标条目已正确索引

#### 技术总结

| 指标 | 修复前 | 修复后 | 改进 |
|------|--------|--------|------|
| **索引条目数** | 296,080 | 308,129 | +12,049 |
| **扫描DB文件** | 1对 (en/zh) | 110对 (en/zh) | ×110 |
| **缺失文本修复** | - | Quest/POI/BYST 等全覆盖 | ✅ |
| **EN规范化键** | 部分缺失 | 完整 | ✅ |

#### 影响范围
- ✅ 修复所有 v3.1 新增剧情文本匹配问题
- ✅ 补全任务、角色、技能等补充数据库内容
- ✅ 消除 PAK 解包后的目录嵌套隐患
- ✅ 自动适配未来游戏版本的数据结构变化

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
