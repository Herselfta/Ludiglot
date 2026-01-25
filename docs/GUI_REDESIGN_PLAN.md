# GUI重构计划 - 鸣潮风格

## 设计目标
参考鸣潮原生UI风格，实现暗色主题+金色点缀的游戏风格界面

## 配色方案（基于截图）
- 主背景色: `#0f1419` (深蓝黑)
- 次背景色: `#1a2332` (暗蓝灰)
- 边框颜色: `#2d3748` (中灰蓝)
- 标题/强调色: `#d4af37` (金色)
- 普通文本: `#e2e8f0` (浅灰白)
- 次要文本: `#94a3b8` (灰蓝)
- 高亮色: `#fbbf24` (亮金)

## 字体方案
### 思源字体集成
- **字体**: 思源宋体 (Noto Serif CJK SC)
- **许可**: SIL Open Font License 1.1 (可商用、可打包)
- **下载源**: [GitHub Releases](https://github.com/notofonts/noto-cjk/releases)
- **文件**: `NotoSerifCJKsc-Regular.otf` (~8MB)

### 实现方式
1. 下载字体到 `assets/fonts/` 目录
2. 使用 QFontDatabase 动态加载
3. 设置为全局默认字体

## QSS样式更新

### 主窗口容器
```qss
#OverlayRoot {
    background-color: #0f1419;
    border: 2px solid #d4af37;
    border-radius: 8px;
}
```

### 标题标签
```qss
#Title {
    color: #d4af37;
    font-size: 16pt;
    font-weight: bold;
    padding: 4px 0;
}
```

### 源文本框
```qss
#SourceText {
    background-color: #1a2332;
    color: #94a3b8;
    border: 1px solid #2d3748;
    border-radius: 4px;
    padding: 8px;
    font-size: 11pt;
}
```

### 中文文本框（支持HTML）
```qss
#AccentText {
    background-color: #1a2332;
    color: #e2e8f0;
    border: 1px solid #d4af37;
    border-radius: 4px;
    padding: 12px;
    font-size: 13pt;
    line-height: 1.6;
}
```

### 按钮
```qss
QPushButton {
    background-color: #1a2332;
    color: #d4af37;
    border: 1px solid #d4af37;
    border-radius: 4px;
    padding: 6px 16px;
    font-size: 10pt;
}

QPushButton:hover {
    background-color: #2d3748;
    border-color: #fbbf24;
}

QPushButton:pressed {
    background-color: #d4af37;
    color: #0f1419;
}

QPushButton:disabled {
    background-color: #1a2332;
    color: #4a5568;
    border-color: #2d3748;
}
```

## HTML渲染修复

### 问题诊断
1. QTextEdit 的 QSS 样式覆盖了 HTML 的 inline style
2. 需要使用 `!important` 或修改渲染方式

### 解决方案
```python
def _convert_game_html(self, text: str) -> str:
    """转换游戏HTML并包装为完整HTML文档。"""
    import re
    
    # 替换颜色标签
    text = re.sub(
        r'<color=(#[0-9a-fA-F]{6})>(.*?)</color>',
        r'<span style="color: \1">\2</span>',
        text
    )
    
    # 包装为完整HTML，确保样式优先级
    html = f'''
    <html>
    <head>
        <style>
            body {{
                font-family: "Noto Serif CJK SC", "SimSun", serif;
                color: #e2e8f0;
                line-height: 1.6;
                margin: 0;
                padding: 0;
            }}
            span {{
                /* 强制应用颜色 */
            }}
        </style>
    </head>
    <body>
        {text.replace(chr(10), '<br>')}
    </body>
    </html>
    '''
    return html
```

## 实现步骤

### 步骤1: 下载字体
```bash
# 下载思源宋体
curl -L -o assets/fonts/NotoSerifCJKsc-Regular.otf \
  https://github.com/notofonts/noto-cjk/releases/download/Serif2.002/NotoSerifCJKsc-Regular.otf
```

### 步骤2: 更新字体加载
```python
def _load_fonts(self) -> None:
    """加载自定义字体"""
    font_path = Path(__file__).parent.parent.parent / "assets" / "fonts" / "NotoSerifCJKsc-Regular.otf"
    if font_path.exists():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                self.setFont(QFont(families[0], 11))
                print(f"[FONT] 已加载: {families[0]}")
```

### 步骤3: 更新QSS文件
替换 `src/ludiglot/ui/style.qss` 的全部内容

### 步骤4: 修复HTML渲染
更新 `_convert_game_html()` 方法，使用完整HTML文档

### 步骤5: 测试验证
1. 启动应用检查字体是否加载
2. 捕获包含HTML标签的文本
3. 验证颜色和样式是否正确显示

## 许可证合规

### 思源字体许可
```
Copyright © 2014-2021 Adobe (http://www.adobe.com/).

Licensed under the SIL Open Font License, Version 1.1
- ✅ 可商业使用
- ✅ 可修改和再分发
- ✅ 可嵌入应用程序
- ⚠️  必须保留许可证文件（assets/fonts/OFL.txt）
```

### 合规措施
1. 添加 `assets/fonts/OFL.txt` 许可证文件
2. 更新 `THIRD_PARTY_NOTICES.md`
3. 在 README 中说明字体来源
