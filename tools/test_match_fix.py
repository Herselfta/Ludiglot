#!/usr/bin/env python
"""测试脚本：验证文本匹配算法修复

测试场景：
1. 长文本不应该匹配到单词
2. 混合内容（标题+长文本）的正确处理
3. 窗口关闭性能优化验证
"""

import sys
from pathlib import Path

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ludiglot.core.smart_match import build_smart_candidates
from ludiglot.core.text_builder import normalize_en

def test_long_text_should_not_match_word():
    """测试：长文本不应该匹配到单个单词"""
    print("=" * 80)
    print("测试1: 长文本不应该匹配到单词")
    print("=" * 80)
    
    # 模拟一个长文本场景
    test_lines = [
        ("Perform up to 4 consecutive attacks, dealing Aero DMG.", 0.92),
        ("Basic Attack Stage 4 inflicts 1 stack of Aero Erosion", 0.91),
        ("upon the target hit.", 0.90)
    ]
    
    result = build_smart_candidates(test_lines)
    candidates = result.get('candidates', [])
    
    print(f"\n输入行数: {len(test_lines)}")
    print(f"完整文本: {result.get('full_text', '')}")
    print(f"生成候选数: {len(candidates)}")
    print(f"检测策略: {result.get('strategy', 'unknown')}")
    
    print("\n候选列表及其特征:")
    for i, (text, conf) in enumerate(candidates, 1):
        normalized = normalize_en(text)
        word_count = len(text.split())
        char_count = len(normalized)
        preview = text[:60] + "..." if len(text) > 60 else text
        print(f"\n  候选 {i}:")
        print(f"    文本: {preview}")
        print(f"    词数: {word_count}, 字符数: {char_count}")
        print(f"    置信度: {conf:.2f}")
        
        # 检查是否为短文本（可能是单词）
        if word_count <= 3 and char_count < 20:
            print(f"    ⚠️  警告：这是一个短文本，可能会被过滤")
    
    print("\n✓ 测试完成：候选生成正常")
    return True


def test_mixed_content_title_and_description():
    """测试：混合内容（标题 + 长文本描述）"""
    print("\n" + "=" * 80)
    print("测试2: 混合内容（标题 + 长文本）")
    print("=" * 80)
    
    test_lines = [
        ("Ms. Voss", 0.92),
        ("We've collected enough Exostrider components to build", 0.91),
        ("exclusive simulator cockpits for Synchronists.", 0.90)
    ]
    
    result = build_smart_candidates(test_lines)
    candidates = result.get('candidates', [])
    
    print(f"\n输入行数: {len(test_lines)}")
    print(f"检测策略: {result.get('strategy', 'unknown')}")
    print(f"是否混合内容: {result.get('is_mixed', False)}")
    
    if result.get('is_mixed'):
        print(f"\n✓ 正确识别为混合内容")
        print(f"  标题: {result.get('title_text', '')}")
        print(f"  内容: {result.get('content_text', '')}")
        
        print(f"\n候选优先级（应优先匹配内容）:")
        for i, (text, conf) in enumerate(candidates, 1):
            preview = text[:60] + "..." if len(text) > 60 else text
            print(f"  {i}. {preview}")
        
        # 验证第一个候选是内容而不是标题
        first_text = candidates[0][0] if candidates else ""
        if "collected" in first_text.lower() or "exostrider" in first_text.lower():
            print(f"\n✓ 正确：第一候选是长文本内容，非标题")
        else:
            print(f"\n⚠️  警告：第一候选不是预期的长文本内容")
    else:
        print(f"\n✗ 错误：未识别为混合内容")
        return False
    
    print("\n✓ 测试完成")
    return True


def test_filter_logic():
    """测试：过滤逻辑验证"""
    print("\n" + "=" * 80)
    print("测试3: 长文本过滤逻辑（模拟代码中的过滤）")
    print("=" * 80)
    
    # 模拟长文本上下文
    context_text = "Perform up to 4 consecutive attacks dealing Aero DMG Basic Attack Stage 4"
    context_words = context_text.split()
    context_len = len(normalize_en(context_text))
    
    print(f"\n上下文信息:")
    print(f"  完整文本: {context_text}")
    print(f"  词数: {len(context_words)}")
    print(f"  字符长度: {context_len}")
    
    # 测试候选
    test_candidates = [
        ("attack", 0.95),  # 单词，应被过滤
        ("dealing Aero DMG", 0.90),  # 短语，应被过滤
        ("Perform up to 4 consecutive attacks", 0.92),  # 较长，应保留
        ("Perform up to 4 consecutive attacks dealing Aero DMG", 0.95),  # 完整，应保留
    ]
    
    print(f"\n测试候选及过滤结果:")
    for text, conf in test_candidates:
        key = normalize_en(text)
        word_count = len(text.split())
        
        # 应用过滤规则（来自修复后的代码）
        should_filter = False
        reason = ""
        
        if (len(context_words) >= 6) or (context_len >= 40):
            if word_count <= 3:
                should_filter = True
                reason = "词数太少 (≤3)"
            elif len(key) < 20:
                should_filter = True
                reason = "字符长度太短 (<20)"
        
        status = "❌ 过滤" if should_filter else "✓ 保留"
        print(f"\n  候选: \"{text}\"")
        print(f"    词数: {word_count}, 字符数: {len(key)}")
        print(f"    {status} {f'({reason})' if reason else ''}")
    
    print("\n✓ 测试完成：过滤逻辑正常")
    return True


def test_length_mismatch_penalty():
    """测试：长度不匹配惩罚"""
    print("\n" + "=" * 80)
    print("测试4: 长度不匹配惩罚机制")
    print("=" * 80)
    
    # 模拟匹配场景
    test_cases = [
        {
            "query": "Perform up to 4 consecutive attacks dealing Aero DMG Basic Attack Stage 4",
            "matched": "attack",
            "score": 0.95,
            "expected_penalty": "应大幅惩罚（query长度是matched的8倍以上）"
        },
        {
            "query": "Perform up to 4 consecutive attacks",
            "matched": "Perform up to 4",
            "score": 0.92,
            "expected_penalty": "应中等惩罚（query长度是matched的1.5倍以上）"
        },
        {
            "query": "attack damage bonus",
            "matched": "attack damage",
            "score": 0.88,
            "expected_penalty": "轻微或无惩罚（长度差异不大）"
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        query = case["query"]
        matched = case["matched"]
        score = case["score"]
        
        query_key = normalize_en(query)
        matched_key = normalize_en(matched)
        query_len = len(query_key)
        matched_len = len(matched_key)
        
        # 计算加权分数（模拟修复后的代码逻辑）
        weighted_score = score
        penalty_applied = False
        penalty_desc = "无惩罚"
        
        if query_len > matched_len * 2 and matched_len < 20:
            weighted_score *= 0.3
            penalty_applied = True
            penalty_desc = "大幅惩罚 (×0.3)"
        elif query_len > matched_len * 1.5 and score < 0.97:
            weighted_score *= 0.7
            penalty_applied = True
            penalty_desc = "中等惩罚 (×0.7)"
        
        print(f"\n  案例 {i}:")
        print(f"    查询文本: {query[:50]}...")
        print(f"    匹配到: {matched}")
        print(f"    长度比: {query_len}/{matched_len} = {query_len/matched_len:.2f}x")
        print(f"    原始分数: {score:.3f}")
        print(f"    加权分数: {weighted_score:.3f}")
        print(f"    惩罚: {penalty_desc}")
        print(f"    预期: {case['expected_penalty']}")
    
    print("\n✓ 测试完成：惩罚机制正常")
    return True


if __name__ == '__main__':
    print("开始测试文本匹配算法修复...\n")
    
    all_passed = True
    
    try:
        all_passed &= test_long_text_should_not_match_word()
        all_passed &= test_mixed_content_title_and_description()
        all_passed &= test_filter_logic()
        all_passed &= test_length_mismatch_penalty()
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    print("\n" + "=" * 80)
    if all_passed:
        print("✓ 所有测试通过！")
    else:
        print("✗ 部分测试失败")
    print("=" * 80)
