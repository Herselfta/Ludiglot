"""Test GLM-OCR backend with TestOCR.png and match against DB."""
import sys
import json
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from ludiglot.core.ocr import OCREngine, group_ocr_lines
from ludiglot.core.matcher import TextMatcher, normalize_en


def main():
    root_dir = project_root
    image_path = root_dir / "cache" / "capture.png"
    db_path = root_dir / "cache" / "game_text_db.json"

    if not image_path.exists():
        print(f"Error: Image not found at {image_path}")
        return

    print(f"--- OCR on {image_path.name} with GLM-OCR (Ollama) backend ---")
    engine = OCREngine(
        lang="en",
        mode="gpu",
        glm_endpoint="http://127.0.0.1:11434",
        glm_ollama_model="glm-ocr:q8_0",
    )
    engine.initialize()

    start_time = time.time()
    raw_lines = engine.recognize_with_boxes(image_path, backend="glm_ollama")
    elapsed = time.time() - start_time
    print(f"OCR Time: {elapsed:.2f}s, backend: {engine.last_backend}")

    print("\nRaw Box Lines from GLM-OCR:")
    for i, line in enumerate(raw_lines):
        text = line.get("text", "")
        conf = line.get("conf", 0.0)
        box = line.get("box")
        print(f"  [{i}] text={repr(text)}, conf={conf:.2f}, box={box}")

    print("\n--- Grouping ---")
    grouped = group_ocr_lines(raw_lines, lang="en")
    print("Grouped:")
    for text, conf in grouped:
        print(f"  [{repr(text)}] conf={conf:.3f}")

    if not grouped:
        print("No text found after grouping.")
        return

    print("\n--- Matching ---")
    if not db_path.exists():
        print("DB not found.")
        return

    with open(db_path, "r", encoding="utf-8") as f:
        db_data = json.load(f)

    matcher = TextMatcher(db_data)
    match_result = matcher.match(grouped)

    if match_result:
        print("\nMatch Found!")
        print(f"  Matched Key: {match_result.get('_matched_key')}")
        print(f"  Score: {match_result.get('_score', match_result.get('score'))}")
        full_query = normalize_en(" ".join(t for t, _ in grouped))
        print(f"  Full query key: {full_query}")
        print(f"  Official EN: {match_result.get('en', '')}")
        print(f"  Official CN: {match_result.get('zh', '')}")
    else:
        print("\nNo Match Found.")
        full_query = normalize_en(" ".join(t for t, _ in grouped))
        print(f"  Full query key: {full_query}")


if __name__ == "__main__":
    main()
