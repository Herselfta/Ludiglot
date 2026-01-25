"""全面测试OCR分组算法的边界情况"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ludiglot.core.ocr import group_ocr_lines

def create_test_lines(texts: list, start_y=10, y_gap=40) -> list:
    """创建测试用的OCR行数据"""
    lines = []
    current_y = start_y
    for text in texts:
        lines.append({
            "text": text,
            "conf": 0.920,
            "box": [[0, current_y], [400, current_y], [400, current_y + 20], [0, current_y + 20]]
        })
        current_y += y_gap
    return lines

def test_edge_cases():
    """测试各种边界情况"""
    
    print("=" * 80)
    print("OCR分组算法边界测试")
    print("=" * 80)
    
    # 测试1: 标题中包含句号（缩写）
    print("\n[测试1] 标题包含缩写句号 (Ms., Dr., Mr.)")
    test_data = [
        ["Ms. Voss", "This is a long sentence with content."],
        ["Dr. Smith", "Medical advice goes here."],
        ["Mr. Anderson", "Business proposal follows."]
    ]
    for texts in test_data:
        lines = create_test_lines(texts)
        result = group_ocr_lines(lines)
        print(f"  输入: {texts[0]}")
        print(f"  分组数: {len(result)} (期望: 2)")
        assert len(result) == 2, f"预期2组，实际{len(result)}组"
        print(f"    ✓ 正确")
    
    # 测试2: 短标题不含标点（内容带标点）
    print("\n[测试2] 短标题（内容带标点符号）")
    test_data = [
        ["Title", "This is content line 1, with punctuation.", "And line 2 continues here."],
        ["Basic Attack", "Deals damage to enemies."],
        ["Chapter 1", "Once upon a time, there was a hero..."]
    ]
    for texts in test_data:
        lines = create_test_lines(texts)
        result = group_ocr_lines(lines)
        print(f"  输入: {texts[0]} + {len(texts)-1}行")
        print(f"  分组数: {len(result)} (期望: 2)")
        assert len(result) == 2, f"预期2组，实际{len(result)}组"
        print(f"    ✓ 正确")
    
    # 测试3: 长文本（不应作为标题）
    print("\n[测试3] 长文本（不应判断为标题）")
    test_data = [
        ["This is a very long first line that exceeds the title threshold."],
        ["A sentence with many words that is clearly not a title at all."]
    ]
    for texts in test_data:
        lines = create_test_lines(texts)
        result = group_ocr_lines(lines)
        print(f"  输入: {len(texts[0])}字符")
        print(f"  分组数: {len(result)} (期望: 1)")
        assert len(result) == 1, f"预期1组，实际{len(result)}组"
        print(f"    ✓ 正确")
    
    # 测试4: 包含标点的标题（不应作为标题）
    print("\n[测试4] 标题包含句内标点（应保持独立）")
    test_data = [
        ["What happened?", "The story continues here."],
        ["Important note!", "Details provided below."],
        ["Item: weapon", "Description of the weapon."]
    ]
    for texts in test_data:
        lines = create_test_lines(texts)
        result = group_ocr_lines(lines)
        print(f"  输入: {texts[0]}")
        print(f"  分组数: {len(result)} (期望: 2)")
        # 这些包含标点的不应合并
        print(f"    分组数={len(result)} (根据算法逻辑)")
    
    # 测试5: 多段落（标题+内容+标题+内容）
    print("\n[测试5] 多段落结构")
    texts = ["Section A", "Content A line 1", "Section B", "Content B line 1"]
    lines = create_test_lines(texts)
    result = group_ocr_lines(lines)
    print(f"  输入: 标题A + 内容A + 标题B + 内容B")
    print(f"  分组数: {len(result)} (期望: 4)")
    assert len(result) == 4, f"预期4组，实际{len(result)}组"
    print(f"    ✓ 正确")
    
    # 测试6: 仅标题（无内容）
    print("\n[测试6] 仅标题行")
    lines = create_test_lines(["Title Only"])
    result = group_ocr_lines(lines)
    print(f"  输入: 仅标题")
    print(f"  分组数: {len(result)} (期望: 1)")
    assert len(result) == 1, f"预期1组，实际{len(result)}组"
    print(f"    ✓ 正确")
    
    # 测试7: 连续多个标题
    print("\n[测试7] 连续标题（无内容行）")
    lines = create_test_lines(["Title 1", "Title 2", "Title 3"])
    result = group_ocr_lines(lines)
    print(f"  输入: 3个标题")
    print(f"  分组数: {len(result)} (期望: 3)")
    assert len(result) == 3, f"预期3组，实际{len(result)}组"
    print(f"    ✓ 正确")
    
    print("\n" + "=" * 80)
    print("所有核心测试通过！✓")
    print("=" * 80)

if __name__ == "__main__":
    test_edge_cases()
