
import json
import os
from pathlib import Path
from ludiglot.core.config import load_config
from ludiglot.core.wwise_hash import WwiseHash
from ludiglot.adapters.wuthering_waves.audio_strategy import WutheringAudioStrategy

def test_resolve():
    cfg = load_config(Path(r"e:\Ludiglot\config\settings.json"))
    strategy = WutheringAudioStrategy()
    text_key = "FavorWord_150108_Content"
    
    # 模拟 _resolve_events_for_text_key 的逻辑
    candidates = []
    
    # 1. PlotAudio
    plot_json = Path(r"e:\Ludiglot\data\ConfigDB\PlotAudio.json")
    if plot_json.exists():
        data = json.loads(plot_json.read_text(encoding="utf-8"))
        for item in (data if isinstance(data, list) else data.get("Items", [])):
            if (item.get("TextKey") or item.get("Name")) == text_key:
                candidates.append(item["Voice"])
    
    # 2. Voice Map (Blob 提取)
    vmap_path = Path(r"e:\Ludiglot\cache\voice_map_v6.json")
    if vmap_path.exists():
        vmap = json.loads(vmap_path.read_text(encoding="utf-8"))["mapping"]
        extra = vmap.get(text_key, [])
        for ev in extra:
            if ev not in candidates:
                candidates.append(ev)
    
    print(f"--- Raw candidates from DB for {text_key} ---")
    for c in candidates:
        print(f"  Event: {c}")

    # 性别过滤逻辑演练
    pref = "female"
    f_words = ["_f", "nvzhu", "roverf", "female"]
    m_words = ["_m", "nanzhu", "roverm", "male"]
    
    matching = [c for c in candidates if any(w in c.lower() for w in f_words)]
    print(f"\n--- Female matched candidates ---")
    for m in matching:
        h = strategy.hash_name(m)
        print(f"  {m} -> Hash: {h}")
        
    non_matching = [c for c in candidates if c not in matching]
    print(f"\n--- Other candidates (Male/Neutral) ---")
    for n in non_matching:
        h = strategy.hash_name(n)
        print(f"  {n} -> Hash: {h}")

if __name__ == "__main__":
    test_resolve()
