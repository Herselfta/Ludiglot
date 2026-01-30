
import json
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).parents[1] / "src"))
from ludiglot.core.wwise_hash import WwiseHash
from ludiglot.core.config import load_config

def debug_resolver_state(key):
    config_path = Path("e:/Ludiglot/config/settings.json")
    if not config_path.exists():
        print("Config not found")
        return
    config = load_config(config_path)
    
    print(f"--- Debugging {key} ---")
    
    # Check PlotAudio (Stage 0)
    from ludiglot.core.text_builder import load_plot_audio_map
    plot_map = load_plot_audio_map(config.data_root)
    print(f"PlotAudio result: {plot_map.get(key)}")
        
    # Check AudioResolver logic
    from ludiglot.core.audio_resolver import AudioResolver
    resolver = AudioResolver(config)
    candidates = resolver.get_candidates(key)
    print("\nCandidates & Hashes:")
    h_obj = WwiseHash()
    for c in candidates:
        h = h_obj.hash_int(c)
        mark = " <--- PLAYED" if h == 4258170280 else ""
        print(f"  {c}: {h}{mark}")

if __name__ == "__main__":
    debug_resolver_state("Main_LahaiRoi_3_2_5_22")
