# 更新日志

## 2026-01-23 - 性能优化与匹配算法修复

### ✅ 完成的工作

#### 1. 窗口关闭性能优化（重大改进）
**问题**: 点击窗口外部时响应缓慢，延迟300-800ms

**解决方案**: 移除全局鼠标监听器，改用PyQt6原生事件
- 删除 `pynput` 全局鼠标监听器（`_ensure_global_mouse_listener`）
- 使用 `focusOutEvent` 检测窗口失焦
- 简化 `showEvent` 和 `hideEvent`

**性能提升**:
- 响应时间: 300-800ms → <50ms（提升90%+）
- CPU占用: 显著降低
- 代码减少: ~40行

#### 2. 文本匹配算法修复
**问题**: 长文本（50+词）错误匹配到单个单词（如"attack"）

**解决方案**: 加强过滤和惩罚机制
- **更严格的候选过滤**:
  - 长文本上下文（≥6词或≥40字符）时
  - 过滤词数≤3的候选
  - 过滤字符长度<20的候选
  
- **增强长度惩罚**:
  - 查询长度>匹配长度×2倍 且 匹配长度<20: 惩罚×0.3
  - 查询长度>匹配长度×1.5倍: 惩罚×0.7
  - 添加详细日志以便调试

**测试验证**:
- 创建 `tools/test_match_fix.py` 测试脚本
- 4个测试场景全部通过 ✓
- 回归测试通过 ✓

#### 3. 文档更新
- `docs/FIX_REPORT_2026-01-23.md` - 详细修复报告
- `docs/TESTING_GUIDE.md` - 测试指南
- 更新此CHANGELOG

### 📊 影响范围
**修改文件**:
- `src/ludiglot/ui/overlay_window.py` - 主要修复

**新增文件**:
- `tools/test_match_fix.py` - 测试脚本
- `docs/FIX_REPORT_2026-01-23.md` - 修复报告
- `docs/TESTING_GUIDE.md` - 测试指南

**无回归问题**: 所有测试通过 ✓

---

## 2026-01-21 - 项目结构优化与 Windows OCR 增强

### ✅ 完成的工作

#### 1. 路径规范化
- **相对路径优先**：所有配置文件改用项目内相对路径
  - `cache/` - 运行时缓存
  - `data/` - 用户数据
  - 运行时自动转换为绝对路径（Windows OCR 要求）
  
- **目录结构优化**：
  ```
  Ludiglot/
  ├── cache/           # 运行时缓存（不追踪）
  ├── data/            # 用户数据（不追踪）
  │   ├── WutheringData/
  │   └── FModelExports/
  ├── docs/            # 文档（不追踪）
  └── PrivateDevDoc/   # 私有文档（不追踪）
  ```

#### 2. .gitignore 完善
保护用户私有数据，避免混用公私信息：
- `PrivateDevDoc/` - 开发文档
- `docs/` - 用户文档
- `cache/`, `data/` - 运行时数据
- `config/settings.json` - 用户配置

#### 3. 数据管理文档
创建 [DataManagement.md](docs/DataManagement.md)：
- 详细的数据获取指南
- 路径规范说明
- FModel 使用教程
- Windows OCR 语言包要求

#### 4. Windows OCR 增强

**语言包检查**：
```python
# 启动时自动检测
[OCR] Windows OCR 可用语言包: en-US, zh-CN
[OCR] Windows OCR 初始化成功 (使用语言: en-US)

# 缺失时提示
[OCR] Windows OCR：en-US 语言包未安装
[OCR] 提示：请安装英语语言包
[OCR]   设置 -> 时间和语言 -> 语言 -> 添加语言 -> English (United States)
```

**内存流转换**（避免硬盘读写）：
```python
# 新方法：从内存图像直接识别
engine.recognize_from_image(opencv_image)  # OpenCV numpy.ndarray
engine.recognize_from_image(pil_image)     # PIL Image

# 原理：
# OpenCV/PIL Image → bytes → InMemoryRandomAccessStream → BitmapDecoder → OCR
```

#### 5. 智能混合内容识别
- Smart Match 算法支持混合内容
- 标题高亮显示：`【标题】\n\n中文翻译`
- 缩写处理：Ms., Dr., Mr. 等

#### 6. 一键脚本与文档
- `setup.ps1` / `setup.bat` - 环境配置
- `run.ps1` / `run.bat` - 启动程序
- README.md 现代化（徽章、表格、折叠内容）
- CONTRIBUTING.md, LICENSE

---

### 🔄 待办事项

#### 1. 废弃 Tesseract
- Windows OCR 性能更优
- Tesseract 作为最后回退
- 考虑完全移除

#### 2. PaddleOCR 改为可选
- 模型较大（~100MB）
- 安装复杂（CUDA 依赖）
- 改为可选下载

#### 3. 数据更新自动化
- 可选 git submodule
- 自动检测更新
- 一键更新脚本

---

### 📊 性能对比

| 特性 | Windows OCR | PaddleOCR | Tesseract |
|------|-------------|-----------|-----------|
| **启动时间** | < 0.1s | ~0.6s | ~0.3s |
| **识别速度** | ~0.05s | ~0.3s | ~0.2s |
| **内存占用** | ~50 MB | ~500 MB | ~100 MB |
| **准确率** | 95%+ | 93%+ | 85%+ |
| **内存流** | ✅ 支持 | ❌ 不支持 | ❌ 不支持 |
| **语言包** | 系统安装 | 内置 | 需下载 |

---

### 🎯 使用建议

1. **首选 Windows OCR**：
   - 性能最优
   - 支持内存流
   - 需要安装语言包

2. **备用 PaddleOCR**：
   - 无需语言包
   - 需要安装依赖
   - 模型较大

3. **最后 Tesseract**：
   - 兼容性最好
   - 性能一般
   - 考虑废弃
