import sys
from pathlib import Path
from PIL import Image

# Mocking the environment to run the test
project_root = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(project_root))

from ludiglot.core.ocr import OCREngine, group_ocr_lines

def main():
    print("--- Testing OCR Pipeline (Dual-Pass + Geometric Grouping Phase 2) ---")
    
    image_path = Path("cache") / "capture.png"
    if not image_path.exists():
        print("capture.png not found")
        return

    # Initialize Engine
    engine = OCREngine(lang="en", mode="auto")
    engine.initialize()
    
    try:
        data = image_path.read_bytes()
        import io
        pil_img = Image.open(io.BytesIO(data))
        print(f"Image Size: {pil_img.size}")

        print("Running recognize_with_boxes(img_obj)...")
        box_lines = engine.recognize_with_boxes(pil_img)
        
        print(f"Raw Box Lines: {len(box_lines)}")
        for i, l in enumerate(box_lines):
            print(f"  Box {i}: '{l.get('text')}' Box={l.get('box')}")
            
        # 2. Test group_ocr_lines
        print("\nRunning group_ocr_lines(box_lines)...")
        final_output = group_ocr_lines(box_lines)
        
        print("\n=== FINAL GROUPED OUTPUT ===")
        for text, conf in final_output:
            print(f"  [Conf: {conf:.2f}] {text}")
            
        with open("debug_ocr_output.txt", "w", encoding="utf-8") as f:
            f.write("--- Testing OCR Pipeline (Dual-Pass + Geometric Grouping) ---\n")
            f.write(f"Image Size: {Image.open(image_path).size}\n")
            f.write("Running recognize_with_boxes(img_obj)...\n")
            f.write(f"Raw Box Lines: {len(box_lines)}\n")
            for i, l in enumerate(box_lines):
                f.write(f"  Box {i}: '{l.get('text')}' Box={l.get('box')}\n")
            f.write("\nRunning group_ocr_lines(box_lines)...\n")
            f.write("\n=== FINAL GROUPED OUTPUT ===\n")
            for text, conf in final_output:
                f.write(f"  [Conf: {conf:.2f}] {text}\n")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
