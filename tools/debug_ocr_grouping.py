"""测试 capture.png 的 OCR 分组算法"""
import sys
from pathlib import Path

# 添加 src 路径
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
    
    # 识别文本框
    print("=" * 80)
    print("原始 OCR 识别结果:")
    print("=" * 80)
    lines = ocr.recognize_with_boxes(str(img_path))
    
    for i, line in enumerate(lines):
        text = line.get("text", "")
        conf = line.get("conf", 0.0)
        box = line.get("box", [])
        if box and len(box) >= 4:
            ys = [pt[1] for pt in box]
            y_min, y_max = min(ys), max(ys)
            print(f"[{i:2d}] y={y_min:3.0f}-{y_max:3.0f} conf={conf:.3f} | {text}")
        else:
            print(f"[{i:2d}] conf={conf:.3f} | {text}")
    
    print("\n" + "=" * 80)
    print("分组后的行文本:")
    print("=" * 80)
    grouped = group_ocr_lines(lines)
    for i, (text, conf) in enumerate(grouped):
        print(f"行 {i+1} (conf={conf:.3f}): {text}")
    
    print("\n" + "=" * 80)
    print("后端使用:", ocr.last_backend if hasattr(ocr, 'last_backend') else "未知")
    print("=" * 80)

if __name__ == "__main__":
    main()
