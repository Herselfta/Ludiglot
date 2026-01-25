# 剩余任务实施计划

## 任务2: 匹配算法优化

### 当前问题
- "Expectation Error" 技能描述匹配到错误的中文条目

### 诊断步骤
1. 查看日志中的匹配得分
2. 检查数据库中"Expectation Error"的实际内容
3. 对比OCR识别结果与数据库条目的相似度

### 优化方案
- 增加标题匹配权重
- 优化长文本匹配算法
- 添加多候选结果评分机制

## 任务5: GUI第一栏显示原文

### 需求分析
- 当前source_label显示的是处理后的查询键（规范化后）
- 用户需要看到原始英文文本（OCR识别的原文）

### 实现方案
1. 修改数据库构建逻辑，保存原始英文文本
2. 更新显示逻辑，从数据库读取原始文本
3. 如果数据库没有原始文本，回退到当前处理结果

### 数据库字段调整
```python
{
    "normalized_key": "expectation error heal all nearby...",
    "original_en": "Expectation Error\nHeal all nearby Resonators...",  # 新增
    "zh": "【祈望·差错】\n治疗附近所有共鸣者...",
    "matches": [...]
}
```

## 任务6: 音频进度条 + 播放控件整合

### UI设计
```
┌─────────────────────────────────────┐
│ 【技能标题】                        │
│                                     │
│ 中文翻译内容...                     │
│                                     │
├─────────────────────────────────────┤
│ ▶  ━━━●━━━━━━━━━━  00:12 / 00:25   │
└─────────────────────────────────────┘
```

### 控件需求
1. **QSlider** - 可拖动进度条
2. **QPushButton** - 播放/暂停按钮（小型，图标样式）
3. **QLabel** - 时间显示 (当前/总时长)
4. **布局** - 水平布局，紧密集成

### PyQt6实现
```python
# 添加音频控制栏
audio_control_layout = QHBoxLayout()
self.play_pause_btn = QPushButton("▶")
self.play_pause_btn.setObjectName("AudioControl")
self.play_pause_btn.setFixedSize(28, 28)

self.audio_slider = QSlider(Qt.Orientation.Horizontal)
self.audio_slider.setObjectName("AudioSlider")

self.time_label = QLabel("00:00 / 00:00")
self.time_label.setObjectName("TimeLabel")

audio_control_layout.addWidget(self.play_pause_btn)
audio_control_layout.addWidget(self.audio_slider)
audio_control_layout.addWidget(self.time_label)
```

### 功能实现
1. **播放状态同步** - 按钮图标切换（▶ / ⏸）
2. **进度更新** - QTimer每100ms更新一次
3. **拖动控制** - slider.valueChanged信号连接到seek功能
4. **时间格式化** - mm:ss格式显示

### 样式调整
```qss
#AudioControl {
    background-color: transparent;
    color: #94a3b8;
    border: none;
    font-size: 16pt;
    padding: 2px;
}

#AudioControl:hover {
    color: #cbd5e1;
}

#AudioSlider::groove:horizontal {
    background: rgba(45, 55, 72, 120);
    height: 4px;
    border-radius: 2px;
}

#AudioSlider::handle:horizontal {
    background: #94a3b8;
    width: 12px;
    height: 12px;
    border-radius: 6px;
    margin: -4px 0;
}

#TimeLabel {
    color: #6b7280;
    font-size: 9pt;
    min-width: 100px;
}
```

## 实施顺序
1. ✅ 窗口自动弹出修复
2. ✅ OCR后端延迟加载
3. ✅ GUI透明度+去金边
4. ⏳ 匹配算法优化（需要查看实际日志）
5. ⏳ 显示原文（需要重构数据库）
6. ⏳ 音频进度条实现

## 测试步骤
1. 启动应用，捕获"Expectation Error"技能
2. 检查匹配结果和中文翻译是否正确
3. 验证第一栏是否显示原始英文
4. 测试音频播放和进度条交互
