
import sys
import logging
import asyncio
from pathlib import Path
import cv2
import numpy as np
import json
from PIL import Image, ImageOps

# Add src to path
project_root = Path(r"e:\Ludiglot")
sys.path.insert(0, str(project_root / "src"))

from ludiglot.core.config import AppConfig
from ludiglot.core.matcher import TextMatcher
from ludiglot.core.ocr import OCREngine

def debug_callback(msg):
    print(f"[DEBUG] {msg}")

async def test_ocr_match():
    print("=== Testing OCR Matching on capture.png ===")
    config = AppConfig(
        data_root=project_root / ".data",
        en_json=project_root / "data/en.json",
        zh_json=project_root / "data/zh.json",
        db_path=project_root / "cache/game_text_db.json",
        image_path=project_root / "cache/capture.png",
        ocr_lang="en"
    )
    
    # Load DB
    if not config.db_path.exists():
        print(f"DB not found: {config.db_path}")
        return
        
    print(f"Loading DB from {config.db_path}")
    db_data = json.loads(config.db_path.read_text(encoding="utf-8"))
    
    # Init Matcher
    matcher = TextMatcher(db_data)
    matcher.signals = type("Signals", (), {"log": type("Signal", (), {"connect": lambda self, x: None, "emit": lambda self, x: print(f"[MATCHER] {x}")})()})()
    matcher.log_callback = debug_callback
    
    img_path = project_root / "cache/capture.png"
    if not img_path.exists():
        print(f"Error: {img_path} not found!")
        return
        
    print(f"Loading image: {img_path}")
    
    # Define experiments
    experiments = [
        ("Original", lambda img: img),
        ("Gray+Auto", lambda img: ImageOps.autocontrast(img.convert('L'))),
        ("Binary (Thresh 128)", lambda img: img.convert('L').point(lambda p: 255 if p > 128 else 0)),
        ("Inverted (White on Black->Black on White)", lambda img: ImageOps.invert(img.convert('RGB')).convert('L')),
        ("Scaled 3x + Gray", lambda img: ImageOps.autocontrast(img.resize((img.width*3, img.height*3), Image.Resampling.LANCZOS).convert('L'))),
    ]

    # Init OCR
    ocr_backend = OCREngine(lang="en", mode="auto")
    
    print("\n=== STARTING COMPARISON ===")
    
    ori_img = Image.open(img_path)
    
    for name, func in experiments:
        print(f"\n--- Experiment: {name} ---")
        try:
            # Process
            proc_img = func(ori_img)
            # Save for inspection
            debug_path = img_path.parent / f"debug_{name.replace(' ', '_').replace('+','')}.png"
            proc_img.save(debug_path)
            
            # OCR
            # recognize_from_image supports PIL Image directly
            lines = ocr_backend.recognize_from_image(proc_img) 
            
            print(f"Result ({len(lines)} lines):")
            for l in lines:
                print(f"  ['{l.get('text')}'] conf={l.get('conf'):.2f}")
                
        except Exception as e:
            print(f"FAILED: {e}")
            
    print("\n=== END COMPARISON ===")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(test_ocr_match())
