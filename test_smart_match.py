#!/usr/bin/env python
"""测试脚本：验证混合内容识别功能"""

import sys
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from ludiglot.core.smart_match import build_smart_candidates

# 测试用例 1：混合内容（标题 + 长文本）
print("=" * 60)
print("测试用例 1: 混合内容（标题 + 长文本）")
print("=" * 60)

test_lines_1 = [
    ("Ms. Voss", 0.92),
    ("We've collected enough Exostrider components to build exclusive", 0.92),
    ("simulator cockpits for Synchronists.", 0.92)
]

result = build_smart_candidates(test_lines_1)
candidates = result.get('candidates', [])
print(f"\n输入行数: {len(test_lines_1)}")
print(f"生成候选数: {len(candidates)}")
print(f"检测策略: {result.get('strategy', 'unknown')}")
print(f"是否混合内容: {result.get('is_mixed', False)}")
if result.get('is_mixed'):
    print(f"  标题: {result.get('title_text', '')}")
    print(f"  内容: {result.get('content_text', '')[:60]}...")
print("\n候选列表:")
for i, (text, conf) in enumerate(candidates, 1):
    preview = text[:80] + "..." if len(text) > 80 else text
    print(f"  {i}. {preview} (conf={conf:.2f})")

# 测试用例 2：列表模式
print("\n" + "=" * 60)
print("测试用例 2: 列表模式")
print("=" * 60)

test_lines_2 = [
    ("Attack", 0.95),
    ("Defense", 0.93),
    ("HP", 0.96),
    ("Speed", 0.94)
]

result = build_smart_candidates(test_lines_2)
candidates = result.get('candidates', [])
print(f"\n输入行数: {len(test_lines_2)}")
print(f"生成候选数: {len(candidates)}")
print(f"检测策略: {result.get('strategy', 'unknown')}")
print("\n候选列表:")
for i, (text, conf) in enumerate(candidates, 1):
    preview = text[:80] + "..." if len(text) > 80 else text
    print(f"  {i}. {preview} (conf={conf:.2f})")

# 测试用例 3：长文本（无标题）
print("\n" + "=" * 60)
print("测试用例 3: 长文本（无标题）")
print("=" * 60)

test_lines_3 = [
    ("The ancient ruins hold secrets that have been", 0.88),
    ("buried for centuries. Only the brave dare", 0.89),
    ("to explore their mysterious depths.", 0.87)
]

result = build_smart_candidates(test_lines_3)
candidates = result.get('candidates', [])
print(f"\n输入行数: {len(test_lines_3)}")
print(f"生成候选数: {len(candidates)}")
print(f"检测策略: {result.get('strategy', 'unknown')}")
print("\n候选列表:")
for i, (text, conf) in enumerate(candidates, 1):
    preview = text[:80] + "..." if len(text) > 80 else text
    print(f"  {i}. {preview} (conf={conf:.2f})")

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)
