import sys
import os
import json
import time
from pathlib import Path

# Fix encoding for Windows terminals
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from ludiglot.core.ocr import OCREngine, group_ocr_lines
from ludiglot.core.matcher import TextMatcher
from ludiglot.core.config import AppConfig

def main():
    root_dir = project_root
    image_path = root_dir / "cache" / "capture.png"
    db_path = root_dir / "cache" / "game_text_db.json"

    if not image_path.exists():
        print(f"Error: Image not found at {image_path}")
        return

    print(f"--- Step 1: Performing OCR on {image_path.name} ---")
    # Initialize Windows OCR (auto mode)
    engine = OCREngine(lang="en", mode="auto")
    engine.initialize()
    
    # Use recognize_with_boxes to get raw boxes
    start_time = time.time()
    raw_lines = engine.recognize_with_boxes(image_path)
    print(f"OCR Time: {time.time() - start_time:.2f}s")
    
    print("\nRaw OCR Lines:")
    for line in raw_lines:
        text = line.get("text", "")
        conf = line.get("conf", 0.0)
        box = line.get("box")
        print(f"  - [{text}] conf={conf:.2f} box={box}")

    print("\n--- Step 2: Grouping OCR Lines ---")
    grouped = group_ocr_lines(raw_lines, lang="en")
    print("Grouped Results:")
    for text, conf in grouped:
        print(f"  - [{text}] (conf={conf:.3f})")

    if not grouped:
        print("No text found.")
        return

    print("\n--- Step 3: Matching against DB (game_text_db.json) ---")
    if not db_path.exists():
        print("DB not found, skipping matching.")
        return

    # config = AppConfig()
    # Load DB manually
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            db_data = json.load(f)
    except Exception as e:
        print(f"Failed to load DB: {e}")
        return

    matcher = TextMatcher(db_data)
    # matcher.load_db(db_path) # TextMatcher does not have load_db method usually, it takes db in init
    
    match_result = matcher.match(grouped)
    
    if match_result:
        print("\nMatch Found!")
        print(f"  Matched Key: {match_result.get('_matched_key')}")
        print(f"  Score: {match_result.get('score')}")
        from ludiglot.core.matcher import normalize_en
        # Re-construct query for display
        query = " ".join([t[0] for t in grouped])
        print(f"  Query: {normalize_en(query)}")
        print(f"  Official EN: {match_result.get('en', '')}")
        print(f"  Official CN: {match_result.get('zh', '')}")
        print(f"  VO Path: {match_result.get('audio_hash')}")
    else:
        print("\nNo Match Found.")

if __name__ == "__main__":
    main()
