"""最终验证：使用capture.png并显示详细分析"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ludiglot.core.ocr import OCREngine, group_ocr_lines

def main():
    img_path = Path(__file__).parent.parent / "cache" / "capture.png"
    if not img_path.exists():
        print(f"错误: {img_path} 不存在")
        return
    
    # 初始化 OCR
    ocr = OCREngine(lang="en", mode="auto")
    ocr.initialize()
    
    # 识别文本
    lines = ocr.recognize_with_boxes(str(img_path))
    
    print("=" * 80)
    print("最终验证：capture.png OCR分组测试")
    print("=" * 80)
    
    print(f"\n原始OCR识别: {len(lines)} 行")
    for i, line in enumerate(lines):
        text = line.get("text", "")
        print(f"  [{i:2d}] {text[:60]}{'...' if len(text) > 60 else ''}")
    
    # 分组
    grouped = group_ocr_lines(lines)
    
    print(f"\n分组后: {len(grouped)} 组")
    print("-" * 80)
    for i, (text, conf) in enumerate(grouped):
        print(f"\n组 {i+1} (置信度={conf:.3f}):")
        if len(text) > 100:
            print(f"  {text[:100]}...")
            print(f"  ... ({len(text)} 字符)")
        else:
            print(f"  {text}")
    
    print("\n" + "=" * 80)
    print("预期输出:")
    print("  - 第1组: 黄色标题（短文本，如'Basic Attack'）")
    print("  - 第2组: 多行文本合并后的完整描述")
    print("=" * 80)
    
    # 验证
    if len(grouped) == 2:
        title, title_conf = grouped[0]
        content, content_conf = grouped[1]
        
        print("\n✓ 分组数量正确 (2组)")
        print(f"\n✓ 标题: \"{title}\"")
        print(f"  - 字符数: {len(title)}")
        print(f"  - 单词数: {len(title.split())}")
        print(f"  - 评估: {'符合标题特征' if len(title.split()) <= 3 else '较长'}")
        
        print(f"\n✓ 内容长度: {len(content)} 字符")
        print(f"  - 包含标点: {any(ch in content for ch in [',', '.', '!', '?', ';', ':'])}")
        print(f"  - 评估: {'符合内容特征' if len(content) > 50 else '较短内容'}")
        
        print("\n" + "="*80)
        print("测试结论: ✓ 分组算法运行正常！")
        print("="*80)
    else:
        print(f"\n✗ 错误: 期望2组，实际{len(grouped)}组")
        print("需要进一步调试")

if __name__ == "__main__":
    main()
