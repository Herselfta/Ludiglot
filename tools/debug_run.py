"""
Debug script that mirrors the actual runtime audio matching logic.
Uses the same functions as the real application.
"""
import sys
from pathlib import Path
import json
import logging

# Ensure src is in path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from ludiglot.core.config import load_config
from ludiglot.core.ocr import OCREngine, group_ocr_lines
from ludiglot.core.text_builder import normalize_en
from ludiglot.core.search import FuzzySearcher
from ludiglot.core.audio_mapper import AudioCacheIndex

# Import actual runtime functions
from ludiglot.__main__ import (
    _load_db,
    _find_audio,
    _play_audio_for_key,
    _get_voice_event_index,
    _resolve_event_for_text_key,
    _ensure_audio_for_hash,
)
from ludiglot.adapters.wuthering_waves.audio_strategy import WutheringAudioStrategy
from ludiglot.core.audio_extract import find_wem_by_hash

# Configure logging to file
log_file = project_root / "log" / "debug_run.log"
log_file.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG, 
    format='[%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def log(msg):
    print(msg)
    logger.info(msg)

def debug_pipeline():
    cfg = load_config(project_root / "config" / "settings.json")
    db_path = cfg.db_path
    image_path = project_root / "cache" / "capture.png"
    
    if not image_path.exists():
        log(f"Error: {image_path} does not exist. Please place a test image there.")
        return

    log("=" * 70)
    log("=== 1. OCR ===")
    log("=" * 70)
    engine = OCREngine(lang=cfg.ocr_lang, use_gpu=cfg.ocr_gpu, mode=cfg.ocr_mode)
    
    box_lines = engine.recognize_with_boxes(image_path)
    
    # Log RAW OCR output before grouping
    log(f"\nRAW OCR Output ({len(box_lines)} boxes):")
    for i, box in enumerate(box_lines):
        text = box.get("text", "")
        conf = box.get("conf", 0.0)
        box_coords = box.get("box", [])
        log(f"  Box[{i}]: '{text}' (conf={conf:.2f}) coords={box_coords}")
    
    lines = group_ocr_lines(box_lines)
    
    log(f"OCR Groups found: {len(lines)}")
    for i, (txt, c) in enumerate(lines):
        log(f"  [{i}] '{txt}' (conf={c:.2f})")
    
    log("\n" + "=" * 70)
    log("=== 2. Text Search (same as runtime) ===")
    log("=" * 70)
    db = _load_db(db_path)
    searcher = FuzzySearcher()
    
    best_key = None
    best_score = 0.0
    best_original_text = ""
    best_match = None
    
    # Try each group - same logic as cmd_run
    for txt, conf in lines:
        if len(txt.strip()) < 5:
            continue
        if any(char.isdigit() for char in txt) and len([c for c in txt if c.isdigit()]) > len(txt) / 3:
            continue
            
        normalized = normalize_en(txt)
        if normalized in db:
            key, score = normalized, 1.0
        else:
            key, score = searcher.search(normalized, db.keys())
            
        log(f"  Testing '{txt[:50]}...' -> Match: {key} (score={score:.3f})")
        if score > best_score:
            best_score = score
            best_key = key
            best_original_text = txt

    if not best_key or best_score < 0.6:
        log("No good match found among all groups.")
        return

    log(f"\nFinal Selection: '{best_original_text}'")
    log(f"Match Key: {best_key} (score={best_score:.3f})")
    
    result = db[best_key]
    best_match = result['matches'][0]
    text_key = best_match.get('text_key', "")
    audio_event = best_match.get("audio_event")
    audio_hash = best_match.get("audio_hash")
    
    log(f"\nTextKey: {text_key}")
    log(f"Audio Event (from DB): {audio_event}")
    log(f"Audio Hash (from DB): {audio_hash}")
    log(f"Match Details:\n{json.dumps(best_match, indent=2, ensure_ascii=False)}")
    
    log("\n" + "=" * 70)
    log("=== 3. Audio Lookup Analysis ===")
    log("=" * 70)
    
    # Build audio cache index - same as runtime
    cache_index = None
    if cfg.audio_cache_path:
        cache_index = AudioCacheIndex(
            cfg.audio_cache_path,
            index_path=cfg.audio_cache_index_path,
            max_mb=cfg.audio_cache_max_mb,
        )
        cache_index.load()
        cache_index.scan()
        log(f"Audio cache index loaded: {len(cache_index.entries)} entries")
    
    # Show what the strategy would generate
    strategy = WutheringAudioStrategy()
    event_from_db = audio_event or _resolve_event_for_text_key(text_key, cfg.data_root)
    log(f"\nResolved Event: {event_from_db}")
    
    candidates = strategy.build_names(text_key, event_from_db)
    log(f"Strategy candidates ({len(candidates)}):")
    for i, name in enumerate(candidates[:15]):
        h = strategy.hash_name(name)
        log(f"  [{i}] {name} -> hash={h}")
    if len(candidates) > 15:
        log(f"  ... and {len(candidates) - 15} more")
    
    # Check voice event index
    event_index = _get_voice_event_index(cfg)
    if event_index:
        extra = event_index.find_candidates(text_key, event_from_db, limit=8)
        log(f"\nVoice Event Index extra candidates: {extra}")
    else:
        log("\nVoice Event Index: Not available")
    
    log("\n" + "=" * 70)
    log("=== 4. WEM File Search ===")
    log("=" * 70)
    
    # Check if WEM files exist
    log(f"audio_wem_root: {cfg.audio_wem_root}")
    log(f"audio_bnk_root: {cfg.audio_bnk_root}")
    
    if cfg.audio_wem_root and cfg.audio_wem_root.exists():
        # Try to find WEM by hash
        if audio_hash:
            h = int(audio_hash)
            wem_path = find_wem_by_hash(cfg.audio_wem_root, h)
            log(f"find_wem_by_hash({h}): {wem_path}")
        
        # Check for WEM files matching the text_key pattern
        log("\nSearching for WEM files matching text_key pattern:")
        
        # Search in WwiseExternalSource
        if "Media" in str(cfg.audio_wem_root):
            ext_root = cfg.audio_wem_root.parents[1] / "WwiseExternalSource"
        else:
            ext_root = cfg.audio_wem_root.parent / "WwiseExternalSource"
        
        log(f"WwiseExternalSource path: {ext_root}")
        log(f"WwiseExternalSource exists: {ext_root.exists()}")
        
        if ext_root.exists():
            # Search for files matching the text_key
            patterns = [
                f"*{text_key}*",
                f"*LahaiRoi_3_2_5*",
                f"*lahairoi_3_2_5*",
            ]
            for pattern in patterns:
                matches = list(ext_root.glob(pattern))[:5]
                if matches:
                    log(f"  Pattern '{pattern}': {[f.name for f in matches]}")
                else:
                    log(f"  Pattern '{pattern}': No matches")
    
    log("\n" + "=" * 70)
    log("=== 5. Attempting Playback (ACTUAL _play_audio_for_key) ===")
    log("=" * 70)
    
    # Call the ACTUAL runtime function
    success = _play_audio_for_key(
        text_key,
        cfg,
        index=cache_index,
        audio_event=audio_event,
        audio_hash=audio_hash
    )
    
    if success:
        log("\n✅ SUCCESS: Audio played!")
    else:
        log("\n❌ FAILED: Audio not found.")
        log("\n--- Configuration ---")
        log(f"  audio_cache_path: {cfg.audio_cache_path}")
        log(f"  audio_wem_root: {cfg.audio_wem_root}")
        log(f"  audio_bnk_root: {cfg.audio_bnk_root}")
        log(f"  audio_txtp_cache: {cfg.audio_txtp_cache}")
        log(f"  vgmstream_path: {cfg.vgmstream_path}")
        log(f"  wwiser_path: {cfg.wwiser_path}")
        
        # Check if WEM files exist for any candidate hash
        if cfg.audio_wem_root and cfg.audio_wem_root.exists():
            log(f"\n--- WEM Root Analysis ---")
            wem_count = len(list(cfg.audio_wem_root.glob("*.wem")))
            log(f"  Total .wem files in wem_root: {wem_count}")
            
            # Sample files
            wem_files = list(cfg.audio_wem_root.glob("*.wem"))[:10]
            log(f"  Sample WEM files: {[f.name for f in wem_files]}")
        
        # Check if any candidate hash exists as WEM
        log("\n--- Checking candidate hashes in WEM root ---")
        for name in candidates[:5]:
            h = strategy.hash_name(name)
            wem_path = find_wem_by_hash(cfg.audio_wem_root, h) if cfg.audio_wem_root else None
            status = "FOUND" if wem_path else "NOT FOUND"
            log(f"  {name} (hash={h}): {status}")

    log(f"\n\nFull log saved to: {log_file}")


if __name__ == "__main__":
    debug_pipeline()
