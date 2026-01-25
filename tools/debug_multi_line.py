"""调试多行内容合并问题"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ludiglot.core.ocr import group_ocr_lines

# 测试: 标题 + 2行内容
lines = [
    {
        "text": "Title",
        "conf": 0.920,
        "box": [[0, 10], [400, 10], [400, 30], [0, 30]]
    },
    {
        "text": "Content line 1",
        "conf": 0.920,
        "box": [[0, 50], [400, 50], [400, 70], [0, 70]]
    },
    {
        "text": "Content line 2",
        "conf": 0.920,
        "box": [[0, 90], [400, 90], [400, 110], [0, 110]]
    }
]

print("输入:")
for i, line in enumerate(lines):
    print(f"  [{i}] {line['text']}")

result = group_ocr_lines(lines)

print(f"\n输出分组数: {len(result)}")
for i, (text, conf) in enumerate(result):
    print(f"  组 {i+1}: {text}")

print(f"\n期望: 2组 (Title | Content line 1 Content line 2)")
print(f"实际: {len(result)}组")

if len(result) == 2:
    print("✓ 正确!")
else:
    print("✗ 有问题 - 需要修复算法")
    
    # 调试信息
    print("\n调试分析:")
    print("  - 第1行 'Title': 短文本，无标点 → 应识别为标题")
    print("  - 第2行 'Content line 1': 无标点结尾 → ?")
    print("  - 第3行 'Content line 2': 无标点结尾 → ?")
