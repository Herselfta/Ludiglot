
import sys
import io
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter
import numpy as np

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from ludiglot.core.ocr import OCREngine

def main():
    image_path = Path("cache") / "capture.png"
    if not image_path.exists():
        print("capture.png not found")
        return

    print("--- Debugging OCR Refinement ---")
    engine = OCREngine(lang="en", mode="auto")
    engine.initialize()
    
    raw_bytes = image_path.read_bytes()
    pil_img = Image.open(io.BytesIO(raw_bytes))
    w, h = pil_img.size
    print(f"Original: {w}x{h}")
    
    def run_test(name, img_bytes):
        print(f"\n--- {name} ---")
        lines = engine._windows_ocr_recognize_from_bytes(img_bytes)
        # Just print the text lines
        for l in lines:
            print(f"  {l.get('text')}")

    # 1. 2.0x Bilinear (Current Baseline approx)
    # The previous run used 1.5x Bilinear.
    scale = 2.0
    nw, nh = int(w*scale), int(h*scale)
    img = pil_img.resize((nw, nh), Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    run_test("2.0x Bilinear", buf.getvalue())

    # 2. 2.0x Bicubic (Previous better shape but merged spaces)
    img_bc = pil_img.resize((nw, nh), Image.Resampling.BICUBIC)
    buf = io.BytesIO()
    img_bc.save(buf, format='PNG')
    run_test("2.0x Bicubic", buf.getvalue())

    # 3. 2.0x Bicubic + Gamma 1.5 (Thinning)
    # Darken image to reduce blooming of white text
    # Gamma correction: new = (old/255) ^ gamma * 255
    # Gamma > 1 makess shadows/midtones darker.
    # Wait. Text is white, BG is dark.
    # If we want to erode white text, we need to make bright pixels darker?
    # No, usually OCR works on black text on white bg (internally). 
    # Windows OCR handles inversion.
    # If the input is Dark BG, White Text.
    # If we darken midtones (Gamma > 1), we push gray halos to black. This thins the white text.
    # Let's try Gamma 1.5 and 2.0.
    
    def apply_gamma(image, g):
        if image.mode != 'RGB':
            image = image.convert('RGB')
        arr = np.array(image) / 255.0
        arr = arr ** g
        arr = (arr * 255).astype(np.uint8)
        return Image.fromarray(arr)
        
    img_g15 = apply_gamma(img_bc, 1.5)
    buf = io.BytesIO()
    img_g15.save(buf, format='PNG')
    run_test("2.0x Bicubic + Gamma 1.5", buf.getvalue())
    
    img_g06 = apply_gamma(img_bc, 0.6) # Brighten midtones (thicken)
    buf = io.BytesIO()
    img_g06.save(buf, format='PNG')
    run_test("2.0x Bicubic + Gamma 0.6 (Thicken)", buf.getvalue())

    # 4. 2.0x Bicubic + Thresholding/Contrast
    img_cont = ImageOps.autocontrast(img_bc, cutoff=10)
    buf = io.BytesIO()
    img_cont.save(buf, format='PNG')
    run_test("2.0x Bicubic + High Contrast", buf.getvalue())

if __name__ == "__main__":
    main()
