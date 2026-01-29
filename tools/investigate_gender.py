
import json
from pathlib import Path
from ludiglot.core.search import FuzzySearcher
from ludiglot.core.text_builder import normalize_en

def investigate():
    db_path = Path(r"e:\Ludiglot\cache\game_text_db.json")
    voice_map_path = Path(r"e:\Ludiglot\cache\voice_map_v6.json")
    
    db = json.loads(db_path.read_text(encoding="utf-8"))
    query = "This power... it's mysterious, yet reassuring nonetheless."
    norm = normalize_en(query)
    
    if norm in db:
        match = db[norm]["matches"][0]
        text_key = match.get("text_key")
        print(f"Matched TextKey: {text_key}")
        
        # 查找 voice_map
        if voice_map_path.exists():
            v_map = json.loads(voice_map_path.read_text(encoding="utf-8"))["mapping"]
            candidates = v_map.get(text_key, [])
            print(f"Candidates in voice_map: {candidates}")
        else:
            print("voice_map_v6.json not found!")
    else:
        print("Text not found in DB!")

if __name__ == "__main__":
    investigate()
