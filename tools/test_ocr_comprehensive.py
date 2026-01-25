#!/usr/bin/env python
"""综合测试脚本 - 验证 Windows OCR 优先调用机制"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from ludiglot.core.ocr import OCREngine, group_ocr_lines


def create_test_images():
    """创建多个测试图片"""
    cache_dir = Path("cache/test_images")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # 测试1: 简单英文
    img1 = Image.new('RGB', (500, 80), color='white')
    draw1 = ImageDraw.Draw(img1)
    try:
        font = ImageFont.truetype('arial.ttf', 28)
    except:
        font = ImageFont.load_default()
    draw1.text((20, 25), 'Hello World!', fill='black', font=font)
    img1.save(cache_dir / "test1_simple.png")
    
    # 测试2: 长句子
    img2 = Image.new('RGB', (700, 100), color='white')
    draw2 = ImageDraw.Draw(img2)
    draw2.text((20, 30), 'Stop right there! Who are you?', fill='black', font=font)
    img2.save(cache_dir / "test2_long.png")
    
    # 测试3: 多行文本
    img3 = Image.new('RGB', (600, 150), color='white')
    draw3 = ImageDraw.Draw(img3)
    draw3.text((20, 20), 'First line of text', fill='black', font=font)
    draw3.text((20, 70), 'Second line here', fill='black', font=font)
    img3.save(cache_dir / "test3_multiline.png")
    
    return [
        cache_dir / "test1_simple.png",
        cache_dir / "test2_long.png",
        cache_dir / "test3_multiline.png",
    ]


def test_ocr_backends():
    """测试不同后端"""
    print("=" * 70)
    print("Windows OCR 优先调用机制测试")
    print("=" * 70)
    
    # 创建测试图片
    print("\n[准备] 创建测试图片...")
    test_images = create_test_images()
    print(f"[准备] 创建了 {len(test_images)} 个测试图片\n")
    
    # 初始化OCR引擎
    engine = OCREngine(lang='en', mode='auto')
    
    # 测试每个图片
    for idx, img_path in enumerate(test_images, 1):
        print(f"\n{'=' * 70}")
        print(f"测试 {idx}: {img_path.name}")
        print('=' * 70)
        
        # 执行OCR
        box_lines = engine.recognize_with_boxes(img_path)
        lines = group_ocr_lines(box_lines)
        backend_used = getattr(engine, "last_backend", "unknown")
        
        print(f"\n[结果] 后端: {backend_used}")
        print(f"[结果] 识别行数: {len(lines)}")
        print(f"[结果] 内容:")
        for line_idx, (text, conf) in enumerate(lines, 1):
            print(f"  {line_idx}. {text} (置信度={conf:.3f})")
    
    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == '__main__':
    test_ocr_backends()
