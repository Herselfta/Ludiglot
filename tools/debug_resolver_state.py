
import json
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).parents[1] / "src"))
from ludiglot.core.wwise_hash import WwiseHash
from ludiglot.core.config import load_config

def debug_resolver_state():
    config_path = Path("e:/Ludiglot/config/settings.json")
    if not config_path.exists():
        print("Config not found")
        return
    config = load_config(config_path)
    
    key = "Main_LahaiRoi_3_2_5_20"
    print(f"--- Debugging {key} ---")
    
    # Check voice_map
    map_path = Path("e:/Ludiglot/cache/voice_map_v6.json")
    if map_path.exists():
        vmap = json.load(open(map_path, encoding="utf-8"))["mapping"]
        print(f"VoiceMap result: {vmap.get(key)}")
        
    # Check AudioResolver logic
    from ludiglot.core.audio_resolver import AudioResolver
    resolver = AudioResolver(config)
    candidates = resolver.get_candidates(key)
    print("\nCandidates & Hashes:")
    h_obj = WwiseHash()
    for c in candidates:
        h = h_obj.hash_int(c)
        mark = " <--- MATCHES LOG" if h == 756064232 else ""
        print(f"  {c}: {h}{mark}")

if __name__ == "__main__":
    debug_resolver_state()
