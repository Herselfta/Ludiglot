import sys
from pathlib import Path
import json
import logging

# Ensure src is in path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root / "src"))

from ludiglot.core.config import load_config
from ludiglot.core.ocr import OCREngine
from ludiglot.core.text_builder import normalize_en
from ludiglot.core.search import FuzzySearcher
from ludiglot.core.audio_player import AudioPlayer
# Note: SmartMatcher imports removed as it is not available here
from ludiglot.__main__ import _ensure_audio_for_hash, _find_audio, _load_db

# Configure logging to stdout
logging.basicConfig(level=logging.INFO, format='[DEBUG] %(message)s')

def debug_pipeline():
    cfg = load_config(project_root / "config" / "settings.json")
    db_path = cfg.db_path
    image_path = Path("cache/capture.png")
    
    if not image_path.exists():
        print(f"Error: {image_path} does not exist. Please place a test image there.")
        return

    print("=== 1. OCR ===")
    engine = OCREngine(lang=cfg.ocr_lang, use_gpu=cfg.ocr_gpu, mode=cfg.ocr_mode)
    lines = engine.recognize_with_confidence(image_path)
    
    # Combine lines for matching
    text = " ".join([txt for txt, _ in lines])
    conf = sum([c for _, c in lines]) / max(len(lines), 1) if lines else 0.0
    
    print(f"OCR Result: '{text}' (conf={conf:.2f})")
    
    print("\n=== 2. Text Search ===")
    db = _load_db(db_path)
    
    # Simple matching logic for debug
    normalized_text = normalize_en(text)
    print(f"Normalized Text: {normalized_text}")
    
    key = None
    score = 0.0
    
    if normalized_text in db:
        print("Exact match found!")
        key = normalized_text
        score = 1.0
    else:
        searcher = FuzzySearcher()
        key, score = searcher.search(normalized_text, db.keys())
        print(f"Fuzzy Match: {key} (score={score:.3f})")

    if score < 0.6: # loose threshold for debug
        print("No good match found.")
        return

    print(f"Match Key: {key}")
    best_match = db[key]['matches'][0]
    print("Match Details:")
    print(json.dumps(best_match, ensure_ascii=False, indent=2))
    
    text_key = best_match.get('text_key', "")
    annotated_event = best_match.get("audio_event")
    annotated_hash = best_match.get("audio_hash")
    
    print("\n=== 3. Audio Lookup Strategy ===")
    from ludiglot.adapters.wuthering_waves.audio_strategy import WutheringAudioStrategy
    from ludiglot.core.text_builder import load_plot_audio_map
    from ludiglot.core.voice_map import build_voice_map_from_configdb
    
    strategy = WutheringAudioStrategy()
    
    # Re-simulate candidate generation
    candidates = strategy.build_names(text_key, annotated_event)
    # Manually add simple vo_ pattern just in case
    simple_vo = f"vo_{text_key}"
    if simple_vo not in candidates:
        candidates.insert(0, simple_vo)
    print(f"Candidates from TextKey/Event: {candidates}")
    
    # Build hashes
    hashes = []
    for c in candidates:
        try:
             # Handle cases where strategy.hash_name might raise
             h = strategy.hash_name(c)
             hashes.append(h)
        except Exception as e:
             print(f"Error hashing {c}: {e}")
             hashes.append(0)

    print(f"Corresponding hashes: {hashes}")
    
    if annotated_hash:
        print(f"DB Annotated Hash: {annotated_hash}")
        try:
            if int(annotated_hash) not in hashes:
                 print("Warning: DB Hash does not match any candidate hash!")
        except: pass

    print("\n=== 4. File Search ===")
    found_path = None
    
    # Check 1: Annotated Hash
    if annotated_hash:
        h = int(annotated_hash)
        print(f"Checking Hash {h}...")
        path = _find_audio(cfg.audio_cache_path, h)
        if path:
            print(f"  -> Found in cache: {path}")
            found_path = path
        else:
            # Try WEM resolution with event name fallback
            candidate_arg = candidates[0] if candidates else None
            print(f"  -> Not in cache. Searching WEM/External (Event: {candidate_arg})...")
            
            # Pass event_name for fallback search
            path = _ensure_audio_for_hash(
                 cfg.audio_cache_path,
                 cfg.audio_wem_root,
                 cfg.vgmstream_path,
                 h,
                 event_name=candidate_arg
            )
            if path:
                 print(f"  -> Found/Converted: {path}")
                 found_path = path
            else:
                 print("  -> Not found.")

    if not found_path:
        # Check Candidates
        for name in candidates:
            h = strategy.hash_name(name)
            print(f"Checking Candidate '{name}' (Hash {h})...")
            # Reuse logic
            path = _ensure_audio_for_hash(
                 cfg.audio_cache_path,
                 cfg.audio_wem_root,
                 cfg.vgmstream_path,
                 h,
                 event_name=name
            )
            if path:
                print(f"  -> Found: {path}")
                found_path = path
                break
    
    if found_path:
        print(f"\n✅ SUCCESS: Audio ready at {found_path}")
        print("Attempting playback...")
        AudioPlayer().play(str(found_path))
    else:
        print("\n❌ ALL FAILED. Audio not found.")
        print("Debug Info:")
        print(f"  WEM Root: {cfg.audio_wem_root}")
        print(f"  Data Root: {cfg.data_root}")
        if cfg.audio_wem_root and cfg.audio_wem_root.exists():
             # Check if External Source dir exists
             ext_root = cfg.audio_wem_root.parents[1] / "WwiseExternalSource"
             print(f"  Ext Root ({ext_root}) exists: {ext_root.exists()}")
             if ext_root.exists():
                 print("  Ext Root Contents (first 5):")
                 for f in list(ext_root.glob("*.wem"))[:5]:
                     print(f"    - {f.name}")

if __name__ == "__main__":
    debug_pipeline()
