"""测试不同的 OCR 分组场景"""
import sys
from pathlib import Path

# 添加 src 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ludiglot.core.ocr import group_ocr_lines

def test_case(name: str, lines: list):
    """测试一个分组案例"""
    print(f"\n{'='*80}")
    print(f"测试案例: {name}")
    print('='*80)
    print("输入行数:", len(lines))
    for i, line in enumerate(lines):
        print(f"  [{i}] y={line['box'][0][1]:.0f} | {line['text']}")
    
    result = group_ocr_lines(lines)
    print(f"\n输出分组数: {len(result)}")
    for i, (text, conf) in enumerate(result):
        print(f"  组 {i+1} (conf={conf:.3f}):")
        print(f"    {text[:80]}{'...' if len(text) > 80 else ''}")

def main():
    # 案例1: 标题 + 多行内容（对话场景）
    case1 = [
        {
            "text": "Ms. Voss",
            "conf": 0.920,
            "box": [[0, 10], [100, 10], [100, 30], [0, 30]]
        },
        {
            "text": "With training and fine-tuning, you'll boost your",
            "conf": 0.920,
            "box": [[0, 50], [400, 50], [400, 70], [0, 70]]
        },
        {
            "text": "synchronization rate with the Exostrider. That'll be",
            "conf": 0.920,
            "box": [[0, 75], [400, 75], [400, 95], [0, 95]]
        },
        {
            "text": "one of your key courses going forward.",
            "conf": 0.920,
            "box": [[0, 100], [350, 100], [350, 120], [0, 120]]
        }
    ]
    test_case("对话: Ms. Voss + 3行内容", case1)
    
    # 案例2: 技能标题 + 多行描述
    case2 = [
        {
            "text": "Basic Attack",
            "conf": 0.920,
            "box": [[0, 10], [120, 10], [120, 30], [0, 30]]
        },
        {
            "text": "Perform up to 4 consecutive attacks, dealing",
            "conf": 0.920,
            "box": [[0, 50], [400, 50], [400, 70], [0, 70]]
        },
        {
            "text": "Aero DMG. Basic Attack Stage 4 inflicts 1 stack",
            "conf": 0.920,
            "box": [[0, 75], [400, 75], [400, 95], [0, 95]]
        },
        {
            "text": "of Aero Erosion upon the target hit",
            "conf": 0.920,
            "box": [[0, 100], [350, 100], [350, 120], [0, 120]]
        }
    ]
    test_case("技能: Basic Attack + 3行描述", case2)
    
    # 案例3: 长标题（不应视为标题）
    case3 = [
        {
            "text": "This is a very long title that should not be treated as a title.",
            "conf": 0.920,
            "box": [[0, 10], [600, 10], [600, 30], [0, 30]]
        },
        {
            "text": "And this is the next line of content.",
            "conf": 0.920,
            "box": [[0, 50], [400, 50], [400, 70], [0, 70]]
        }
    ]
    test_case("长文本: 不应判断为标题+内容", case3)
    
    # 案例4: 缩写结尾（Ms. 等）
    case4 = [
        {
            "text": "Dr. Smith",
            "conf": 0.920,
            "box": [[0, 10], [100, 10], [100, 30], [0, 30]]
        },
        {
            "text": "Your diagnosis shows improvement.",
            "conf": 0.920,
            "box": [[0, 50], [350, 50], [350, 70], [0, 70]]
        }
    ]
    test_case("缩写: Dr. Smith + 内容", case4)
    
    # 案例5: 单行（无需合并）
    case5 = [
        {
            "text": "Single line of text with no merging needed.",
            "conf": 0.920,
            "box": [[0, 10], [500, 10], [500, 30], [0, 30]]
        }
    ]
    test_case("单行: 无需合并", case5)
    
    # 案例6: 多段落（标题+内容+新标题+新内容）
    case6 = [
        {
            "text": "Section A",
            "conf": 0.920,
            "box": [[0, 10], [100, 10], [100, 30], [0, 30]]
        },
        {
            "text": "Content for section A goes here.",
            "conf": 0.920,
            "box": [[0, 50], [350, 50], [350, 70], [0, 70]]
        },
        {
            "text": "Section B",
            "conf": 0.920,
            "box": [[0, 100], [100, 100], [100, 120], [0, 120]]
        },
        {
            "text": "Content for section B goes here.",
            "conf": 0.920,
            "box": [[0, 140], [350, 140], [350, 160], [0, 160]]
        }
    ]
    test_case("多段: 标题A+内容A+标题B+内容B", case6)

if __name__ == "__main__":
    main()
