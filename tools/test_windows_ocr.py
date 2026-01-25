#!/usr/bin/env python
"""测试 Windows OCR 的独立脚本"""

from pathlib import Path
from ludiglot.core.ocr import OCREngine


def main():
    engine = OCREngine(lang='en')
    test_path = Path('cache/test_windows_ocr.png')
    
    print(f'测试图片: {test_path}')
    print('=' * 60)
    
    # 测试Windows OCR
    engine._init_windows_ocr()
    if engine._windows_ocr:
        lines = engine._windows_ocr_recognize_boxes(test_path)
        print(f'Windows OCR 结果: {len(lines)} 行')
        for line in lines:
            print(f'  - {line["text"]} (conf={line["conf"]})')
    else:
        print('Windows OCR 不可用')
    
    print('=' * 60)


if __name__ == '__main__':
    main()
