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
from ludiglot.core.matcher import TextMatcher
from ludiglot.core.audio_mapper import AudioCacheIndex
from ludiglot.core.audio_player import AudioPlayer
from ludiglot.core.audio_resolver import AudioResolver, get_voice_event_index
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
    db = json.loads(db_path.read_text(encoding="utf-8"))
    matcher = TextMatcher(db, gender_preference=cfg.gender_preference)

    result = None
    best_original_text = ""
    for txt, conf in lines:
        if len(txt.strip()) < 5:
            continue
        candidate = matcher.match([(txt, conf)])
        score = candidate.get("_score", 0.0) if candidate else 0.0
        key = candidate.get("_matched_key", "") if candidate else ""
        log(f"  Testing '{txt[:50]}...' -> Match: {key} (score={score:.3f})")
        if candidate and (result is None or score > result.get("_score", 0.0)):
            result = candidate
            best_original_text = txt

    if not result or result.get("_score", 0.0) < 0.6:
        log("No good match found among all groups.")
        return

    log(f"\nFinal Selection: '{best_original_text}'")
    log(f"Match Key: {result.get('_matched_key')} (score={result.get('_score', 0.0):.3f})")

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
    
    resolver = AudioResolver(cfg, voice_event_index=get_voice_event_index(cfg), audio_index=cache_index)
    candidates = resolver.get_candidates(text_key, audio_event)
    log(f"\nResolver candidates ({len(candidates)}):")
    for i, name in enumerate(candidates[:10]):
        h = resolver.strategy.hash_name(name)
        log(f"  [{i}] {name} -> hash={h}")

    event_index = get_voice_event_index(cfg)
    if event_index:
        ref_event = candidates[0] if candidates else audio_event
        extra = event_index.find_candidates(text_key, ref_event, limit=8)
        log(f"\nVoice Event Index extra candidates: {extra}")
    else:
        log("\nVoice Event Index: Not available")

    log("\n" + "=" * 70)
    log("=== 4. WEM File Search ===")
    log("=" * 70)

    log(f"audio_wem_root: {cfg.audio_wem_root}")
    log(f"audio_bnk_root: {cfg.audio_bnk_root}")

    if cfg.audio_wem_root and cfg.audio_wem_root.exists():
        if audio_hash:
            h = int(audio_hash)
            wem_path = find_wem_by_hash(cfg.audio_wem_root, h)
            log(f"find_wem_by_hash({h}): {wem_path}")

        log("\nSearching for WEM files matching text_key pattern:")
        if "Media" in str(cfg.audio_wem_root):
            ext_root = cfg.audio_wem_root.parents[1] / "WwiseExternalSource"
        else:
            ext_root = cfg.audio_wem_root.parent / "WwiseExternalSource"

        log(f"WwiseExternalSource path: {ext_root}")
        log(f"WwiseExternalSource exists: {ext_root.exists()}")

        if ext_root.exists():
            for pattern in (f"*{text_key}*", f"*{text_key.lower()}*"):
                matches = list(ext_root.glob(pattern))[:5]
                if matches:
                    log(f"  Pattern '{pattern}': {[f.name for f in matches]}")
                else:
                    log(f"  Pattern '{pattern}': No matches")

    log("\n" + "=" * 70)
    log("=== 5. Attempting Playback (AudioResolver) ===")
    log("=" * 70)

    resolution = resolver.resolve(
        text_key,
        db_event=audio_event,
        db_hash=int(audio_hash) if audio_hash else None,
    )
    audio_path = None
    if resolution:
        log(
            f"Resolver result: event={resolution.event_name}, "
            f"hash={resolution.hash_value}, source={resolution.source_type}"
        )
        if resolution.source_type == "cache":
            audio_path = resolver.get_cached_path(resolution.hash_value, resolution.event_name)
        if audio_path is None:
            audio_path = resolver.ensure_playable_audio(
                resolution.hash_value,
                text_key,
                resolution.event_name,
                log_callback=log,
            )

    if audio_path:
        AudioPlayer().play(str(audio_path))
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

        if cfg.audio_wem_root and cfg.audio_wem_root.exists():
            log(f"\n--- WEM Root Analysis ---")
            wem_count = len(list(cfg.audio_wem_root.glob("*.wem")))
            log(f"  Total .wem files in wem_root: {wem_count}")
            wem_files = list(cfg.audio_wem_root.glob("*.wem"))[:10]
            log(f"  Sample WEM files: {[f.name for f in wem_files]}")

        log("\n--- Checking candidate hashes in WEM root ---")
        for name in candidates[:5]:
            h = resolver.strategy.hash_name(name)
            wem_path = find_wem_by_hash(cfg.audio_wem_root, h) if cfg.audio_wem_root else None
            status = "FOUND" if wem_path else "NOT FOUND"
            log(f"  {name} (hash={h}): {status}")
    log(f"\n\nFull log saved to: {log_file}")


if __name__ == "__main__":
    debug_pipeline()
