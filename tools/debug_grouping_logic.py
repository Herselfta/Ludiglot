"""调试 OCR 分组算法"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ludiglot.core.ocr import OCREngine

def test_grouping():
    img_path = Path(__file__).parent.parent / "cache" / "capture.png"
    
    ocr = OCREngine(lang="en", mode="auto")
    ocr.initialize()
    
    lines_raw = ocr.recognize_with_boxes(str(img_path))
    
    print("原始识别:")
    for i, line in enumerate(lines_raw):
        text = line.get("text", "")
        box = line.get("box", [])
        if box and len(box) >= 4:
            ys = [pt[1] for pt in box]
            print(f"[{i}] y={min(ys)}-{max(ys)} | {text}")
    
    # 手动模拟分组逻辑
    items = []
    for item in lines_raw:
        text = item.get("text", "").strip()
        if not text:
            continue
        conf = item.get("conf", 0.0)
        box = item.get("box", [])
        if len(box) >= 4:
            xs = [pt[0] for pt in box]
            ys = [pt[1] for pt in box]
            x1, x2 = float(min(xs)), float(max(xs))
            y1, y2 = float(min(ys)), float(max(ys))
        else:
            x1 = y1 = 0.0
            x2 = y2 = 0.0
        h = max(y2 - y1, 1.0)
        cy = y1 + h / 2.0
        items.append({"text": text, "conf": conf, "x1": x1, "y1": y1, "cy": cy, "h": h})
    
    print("\n提取的 items:")
    for i, item in enumerate(items):
        print(f"[{i}] text='{item['text']}' | cy={item['cy']:.1f} h={item['h']:.1f}")
    
    # 分行逻辑
    items.sort(key=lambda x: x["cy"])
    lines = []
    current = []
    current_y = None
    current_h = None
    
    for idx, item in enumerate(items):
        if not current:
            current = [item]
            current_y = item["cy"]
            current_h = item["h"]
            print(f"\n开始新行: [{idx}] '{item['text']}'")
            continue
        
        threshold = max(12.0, float(current_h) * 0.7)
        distance = abs(item["cy"] - current_y)
        
        print(f"[{idx}] 检查: '{item['text']}' | distance={distance:.1f} threshold={threshold:.1f}")
        
        if current_y is not None and distance <= threshold:
            current.append(item)
            current_y = (current_y + item["cy"]) / 2.0
            current_h = max(float(current_h), float(item["h"]))
            print(f"  → 合并到当前行")
        else:
            lines.append(current)
            print(f"  → 新行（行数={len(lines)}）")
            current = [item]
            current_y = item["cy"]
            current_h = item["h"]
    
    if current:
        lines.append(current)
    
    print(f"\n分行结果: {len(lines)} 行")
    
    # 构建初步输出
    initial_output = []
    for i, line in enumerate(lines):
        line.sort(key=lambda x: x["x1"])
        tokens = [t["text"] for t in line]
        confs = [float(t["conf"]) for t in line]
        text = " ".join(tokens)
        for punct in [",", ".", "!", "?", ";", ":"]:
            text = text.replace(f" {punct}", punct)
        avg_conf = sum(confs) / max(len(confs), 1)
        
        word_count = len(text.split())
        char_count = len(text)
        is_title = word_count <= 3 and char_count <= 30 and not any(ch in text for ch in [',', '.', '!', '?', ':'])
        
        initial_output.append((text, avg_conf, is_title))
        print(f"行 {i+1}: '{text}' | words={word_count} chars={char_count} is_title={is_title}")
    
    # 智能合并
    print("\n智能合并:")
    if len(initial_output) >= 2:
        first_text, first_conf, first_is_title = initial_output[0]
        rest_items = initial_output[1:]
        rest_non_titles = [item for item in rest_items if not item[2]]
        
        print(f"第一行是标题: {first_is_title}")
        print(f"后续非标题行数: {len(rest_non_titles)}")
        
        if first_is_title and len(rest_non_titles) >= 1:
            print("→ 检测到'标题+对话'模式，执行合并")
        else:
            print("→ 非'标题+对话'模式，保持原有分行")

if __name__ == "__main__":
    test_grouping()
