
import json
from pathlib import Path

def check_db_entry(key):
    db_path = Path("e:/Ludiglot/cache/game_text_db.json")
    if not db_path.exists():
        print("DB not found")
        return
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        entry = data.get(key)
        print(f"Entry for {key}: {entry}")

if __name__ == "__main__":
    check_db_entry("Main_LahaiRoi_3_2_5_20")
