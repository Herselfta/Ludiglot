#!/usr/bin/env python
"""快速 GUI 测试 - 验证 Windows OCR 在实际应用中的表现"""

import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget, QPushButton
from PyQt6.QtCore import Qt

from ludiglot.core.ocr import OCREngine, group_ocr_lines


class QuickTestWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Windows OCR 快速测试")
        self.setGeometry(300, 300, 500, 400)
        
        layout = QVBoxLayout()
        
        # 标题
        title = QLabel("Windows OCR 集成测试")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # 状态显示
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("padding: 10px; background: #f0f0f0; border-radius: 5px;")
        layout.addWidget(self.status_label)
        
        # 结果显示
        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("padding: 10px; margin-top: 10px;")
        layout.addWidget(self.result_label)
        
        # 测试按钮
        test_btn = QPushButton("测试 Windows OCR")
        test_btn.clicked.connect(self.run_test)
        test_btn.setStyleSheet("padding: 10px; font-size: 14px; margin-top: 20px;")
        layout.addWidget(test_btn)
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        close_btn.setStyleSheet("padding: 10px; margin-top: 10px;")
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
        self.engine = None
    
    def run_test(self):
        """运行 OCR 测试"""
        self.status_label.setText("🔄 正在测试...")
        self.result_label.setText("")
        
        try:
            # 初始化引擎
            if not self.engine:
                self.status_label.setText("🔄 初始化 OCR 引擎...")
                self.engine = OCREngine(lang='en', mode='auto')
            
            # 测试图片
            test_image = Path('cache/test_windows_ocr.png')
            if not test_image.exists():
                self.result_label.setText("❌ 测试图片不存在，请先运行 test_ocr_comprehensive.py")
                self.status_label.setText("测试失败")
                return
            
            # 执行 OCR
            self.status_label.setText("🔄 正在识别文本...")
            box_lines = self.engine.recognize_with_boxes(test_image)
            lines = group_ocr_lines(box_lines)
            backend = getattr(self.engine, "last_backend", "unknown")
            
            # 显示结果
            if lines:
                result_text = f"✅ 使用后端: <b>{backend}</b><br><br>"
                result_text += f"📝 识别到 {len(lines)} 行文本：<br>"
                for idx, (text, conf) in enumerate(lines, 1):
                    result_text += f"&nbsp;&nbsp;{idx}. {text} <span style='color: gray;'>(置信度={conf:.3f})</span><br>"
                
                self.result_label.setText(result_text)
                self.status_label.setText(f"✅ 测试成功！后端: {backend}")
            else:
                self.result_label.setText("⚠️ 未识别到任何文本")
                self.status_label.setText("测试完成（无结果）")
        
        except Exception as e:
            self.result_label.setText(f"❌ 错误: {str(e)}")
            self.status_label.setText("测试失败")


def main():
    app = QApplication(sys.argv)
    window = QuickTestWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
