"""
智能文本匹配算法 - 支持混合单行标题和多行长文本的场景

优化点：
1. 智能区分单行标题（如"Ms. Voss"）和多行长文本
2. 混合内容时分段处理：第一行单独匹配，后续行拼接匹配
3. 优先返回有语音的条目
4. 保留标题信息用于显示
"""

from __future__ import annotations
from typing import Dict, List, Tuple, Any


def analyze_line_characteristics(text: str, conf: float) -> Dict[str, Any]:
    """分析单行文本的特征"""
    cleaned = text.strip()
    word_count = len(cleaned.split())
    char_count = len(cleaned)
    
    # 判断是否为短标题（排除缩写中的句号，如 Ms., Dr., Mr.）
    is_short = word_count <= 3 and char_count <= 25
    # 移除常见缩写后再检查标点
    test_text = cleaned.replace('Ms.', 'Ms').replace('Mr.', 'Mr').replace('Dr.', 'Dr')
    test_text = test_text.replace('Mrs.', 'Mrs').replace('Prof.', 'Prof').replace('St.', 'St')
    is_title_like = is_short and not any(ch in test_text for ch in [',', '.', '!', '?', ';'])
    
    # 判断是否为长描述
    is_long = word_count >= 6 or char_count >= 40
    has_punctuation = any(ch in cleaned for ch in [',', '.', '!', '?'])
    
    return {
        'text': text,
        'cleaned': cleaned,
        'word_count': word_count,
        'char_count': char_count,
        'is_short': is_short,
        'is_title_like': is_title_like,
        'is_long': is_long,
        'has_punctuation': has_punctuation,
        'conf': conf,
    }


def detect_mixed_content(lines_info: List[Dict[str, Any]]) -> Dict[str, Any]:
    """检测是否为混合内容（标题 + 长文本）"""
    if len(lines_info) < 2:
        return {'is_mixed': False}
    
    first = lines_info[0]
    rest = lines_info[1:]
    
    # 判断：第一行是标题，后续行构成长文本
    if first['is_title_like']:
        rest_word_count = sum(l['word_count'] for l in rest)
        rest_has_long = any(l['is_long'] or l['has_punctuation'] for l in rest)
        
        if rest_word_count >= 6 or rest_has_long:
            return {
                'is_mixed': True,
                'title_line': first,
                'content_lines': rest,
                'combined_words': rest_word_count,
            }
    
    return {'is_mixed': False}


def build_smart_candidates(
    lines: List[Tuple[str, float]], 
    clean_func=None,
    normalize_func=None
) -> Dict[str, Any]:
    """构建智能候选集合
    
    返回:
        {
            'is_mixed': bool,
            'title_text': str,  # 如果是混合内容
            'content_text': str,  # 如果是混合内容
            'full_text': str,  # 完整文本
            'candidates': [(text, conf), ...],  # 待匹配的候选
            'strategy': 'mixed' | 'list' | 'long' | 'single'
        }
    """
    if clean_func is None:
        clean_func = lambda x: x.strip()
    if normalize_func is None:
        normalize_func = lambda x: x.lower().replace(' ', '')
    
    # 分析每行特征
    lines_info = [analyze_line_characteristics(text, conf) for text, conf in lines]
    
    # 检测混合内容
    mixed_info = detect_mixed_content(lines_info)
    
    if mixed_info['is_mixed']:
        # 混合内容：标题 + 描述
        title_line = mixed_info['title_line']
        content_lines = mixed_info['content_lines']
        
        title_text = title_line['cleaned']
        content_text = ' '.join(l['cleaned'] for l in content_lines)
        full_text = f"{title_text} {content_text}"
        
        # 候选：1. 标题单独 2. 内容单独 3. 完整文本
        candidates = [
            (content_text, sum(l['conf'] for l in content_lines) / len(content_lines)),  # 优先内容
            (title_text, title_line['conf']),
            (full_text, sum(l['conf'] for l in lines_info) / len(lines_info)),
        ]
        
        return {
            'is_mixed': True,
            'title_text': title_text,
            'content_text': content_text,
            'full_text': full_text,
            'candidates': candidates,
            'strategy': 'mixed',
        }
    
    # 检测列表模式
    all_short = all(l['is_short'] for l in lines_info)
    if len(lines_info) >= 3 and all_short:
        candidates = [(l['cleaned'], l['conf']) for l in lines_info]
        return {
            'is_mixed': False,
            'full_text': ' '.join(l['cleaned'] for l in lines_info),
            'candidates': candidates,
            'strategy': 'list',
        }
    
    # 长文本模式
    if len(lines_info) >= 2:
        full_text = ' '.join(l['cleaned'] for l in lines_info)
        candidates = [(full_text, sum(l['conf'] for l in lines_info) / len(lines_info))]
        # 添加滑动窗口候选（如果文本很长）
        if len(full_text.split()) >= 10:
            words = full_text.split()
            for start in range(0, len(words) - 5, 3):
                segment = ' '.join(words[start:start+10])
                candidates.append((segment, 0.8))
        return {
            'is_mixed': False,
            'full_text': full_text,
            'candidates': candidates,
            'strategy': 'long',
        }
    
    # 单行模式
    if lines_info:
        l = lines_info[0]
        return {
            'is_mixed': False,
            'full_text': l['cleaned'],
            'candidates': [(l['cleaned'], l['conf'])],
            'strategy': 'single',
        }
    
    return {
        'is_mixed': False,
        'full_text': '',
        'candidates': [],
        'strategy': 'empty',
    }


# 示例用法
if __name__ == '__main__':
    # 测试用例1: 混合内容（标题 + 长文本）
    test_lines_1 = [
        ("Ms. Voss", 0.92),
        ("We've collected enough Exo Strider components", 0.91),
        ("to build exclusive simulator cockpits for Synchronists.", 0.90),
    ]
    
    result = build_smart_candidates(test_lines_1)
    print("测试1 - 混合内容:")
    print(f"  策略: {result['strategy']}")
    print(f"  是否混合: {result['is_mixed']}")
    if result['is_mixed']:
        print(f"  标题: {result['title_text']}")
        print(f"  内容: {result['content_text']}")
    print(f"  候选数: {len(result['candidates'])}")
    print()
    
    # 测试用例2: 列表模式
    test_lines_2 = [
        ("HP", 0.95),
        ("ATK", 0.94),
        ("DEF", 0.93),
    ]
    
    result = build_smart_candidates(test_lines_2)
    print("测试2 - 列表模式:")
    print(f"  策略: {result['strategy']}")
    print(f"  候选数: {len(result['candidates'])}")
    print()
    
    # 测试用例3: 长文本
    test_lines_3 = [
        ("This is a very long sentence that", 0.88),
        ("spans multiple lines and contains", 0.87),
        ("important information about the game.", 0.86),
    ]
    
    result = build_smart_candidates(test_lines_3)
    print("测试3 - 长文本:")
    print(f"  策略: {result['strategy']}")
    print(f"  完整文本: {result['full_text']}")
    print(f"  候选数: {len(result['candidates'])}")
