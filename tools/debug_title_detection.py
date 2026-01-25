"""详细调试分组判断"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ludiglot.core.ocr import OCREngine

def main():
    img_path = Path(__file__).parent.parent / "cache" / "capture.png"
    ocr = OCREngine(lang="en", mode="auto")
    ocr.initialize()
    
    lines = ocr.recognize_with_boxes(str(img_path))
    
    print("=" * 80)
    print("每行的标题判断详情")
    print("=" * 80)
    
    for i, line in enumerate(lines):
        text = line.get("text", "").strip()
        word_count = len(text.split())
        char_count = len(text)
        
        stripped = text.rstrip()
        ends_with_period = stripped.endswith('.')
        has_sentence_punct = any(ch in text for ch in [',', '!', '?', ':'])
        
        is_likely_sentence = has_sentence_punct or ends_with_period
        is_title = word_count <= 3 and char_count <= 30 and not is_likely_sentence
        
        print(f"\n[{i:2d}] {text}")
        print(f"     词数={word_count}, 字符数={char_count}")
        print(f"     句号结尾={ends_with_period}, 句内标点={has_sentence_punct}")
        print(f"     is_likely_sentence={is_likely_sentence}")
        print(f"     → {'标题' if is_title else '内容'}")

if __name__ == "__main__":
    main()
