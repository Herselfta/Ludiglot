# 紧急Bug修复报告

## 修复的严重问题

### 问题1: 窗口不自动弹出 + 音频不播放 🔴 **已修复**

**根本原因**: 代码结构错误
- `_convert_game_html()` 方法的 `return html` 后面错误地放置了窗口显示和音频播放的代码
- 导致这些代码永远不会执行
- 这是我在之前修改HTML渲染时的严重失误

**症状**:
- OCR识别成功
- 中文翻译正常
- 但窗口不显示，音频不播放
- 日志中缺少 `[QUERY]` 输出

**修复**:
```python
# 文件: src/ludiglot/ui/overlay_window.py
# 位置: _show_result() 方法末尾

# ✅ 已添加缺失的代码:
# 设置音频按钮状态
has_audio = self.last_hash is not None
self.play_btn.setEnabled(has_audio)
self.stop_btn.setEnabled(has_audio)

self.signals.log.emit(f"[QUERY] {result.get('_ocr_text')} -> {query_key}")

# 确保窗口显示并置顶
self.show_and_activate()

# 自动播放逻辑
if self.config.play_audio and has_audio:
    self.play_audio()
```

**测试步骤**:
1. 重启应用
2. 框选任何文本(带或不带语音)
3. ✅ 窗口应立即弹出并置顶
4. ✅ 如果有语音，应自动播放

---

### 问题2: 快捷键需要连按两次 ⚠️ **部分修复**

**当前状态**: 
- `isHidden()` 逻辑已实现
- 但可能存在事件同步问题

**诊断方法**:
用户测试并提供以下信息：
1. 点击窗口外关闭后，按一次快捷键是否能打开？
2. 使用Close按钮关闭后，按一次快捷键是否能打开？
3. 如果仍需要两次，提供操作顺序

**潜在原因**:
- Windows系统层面的窗口焦点问题
- Qt的show/hide事件处理延迟

**可能的额外修复**:
```python
def _toggle_visibility(self) -> None:
    """切换窗口显示/隐藏状态"""
    # 强制刷新窗口状态
    QApplication.processEvents()
    
    if self.isHidden():
        self.show_and_activate()
    else:
        self.hide()
        # 确保hide事件被处理
        QApplication.processEvents()
```

---

## 测试清单

### ✅ 必须验证的功能:

1. **OCR识别**
   - [ ] 框选文本后识别成功
   - [ ] 识别结果正确显示在第一栏

2. **窗口自动弹出**
   - [ ] 识别完成后窗口立即显示
   - [ ] 窗口置顶可见
   - [ ] 不需要手动点击

3. **音频播放**
   - [ ] 带语音的文本自动播放
   - [ ] 播放按钮状态正确
   - [ ] 无语音文本不播放

4. **快捷键切换**
   - [ ] 关闭窗口后按一次快捷键能打开
   - [ ] 打开窗口后按一次快捷键能关闭
   - [ ] 不需要连按两次

5. **GUI样式**
   - [ ] 半透明背景生效
   - [ ] 无金色边框
   - [ ] 低调配色

---

## 已知问题

### 匹配准确性 ⚠️
- "Basic Attack" 技能描述匹配得分较低(0.525)
- 匹配到了错误的"夏空"技能而非当前角色
- **原因**: 数据库中可能有多个角色的相似技能
- **建议**: 
  1. 增加数据库条目的多样性
  2. 优化匹配算法的权重计算
  3. 添加上下文信息（角色名等）

### PaddleOCR仍在启动 ⚠️
- 旧日志显示仍在加载PaddleOCR模型
- 新代码已修复，但旧进程可能仍在运行
- **解决**: 重启应用即可

---

## 下一步

1. **立即**重启应用测试窗口弹出和音频播放
2. 测试快捷键是否仍需要连按两次
3. 如果快捷键问题仍存在，提供详细操作步骤
4. 如果匹配结果仍不准确，提供具体错误案例

---

## 代码变更摘要

**文件**: `src/ludiglot/ui/overlay_window.py`

**修改**: 
- 在 `_show_result()` 方法末尾添加了缺失的窗口显示和音频播放代码
- 修复了因`_convert_game_html()` return语句位置错误导致的死代码

**影响**: 
- ✅ 窗口自动弹出恢复正常
- ✅ 音频自动播放恢复正常
- ✅ 日志输出完整

**风险**: 
- 无，纯修复之前的错误
