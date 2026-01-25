from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (str(SRC), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from ludiglot.core.text_builder import normalize_en


def clean_line(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
    return " ".join(cleaned.split()).strip()


def is_list_mode(lines: list[str]) -> bool:
    if len(lines) < 4:
        return False
    cleaned = [clean_line(t) for t in lines if t]
    cleaned = [c for c in cleaned if c]
    if len(cleaned) < 4:
        return False
    lengths = [len(c) for c in cleaned]
    max_len = max(lengths)
    avg_words = sum(len(c.split()) for c in cleaned) / max(len(cleaned), 1)
    return max_len <= 16 and avg_words <= 2.2


def stat_alias_map() -> dict[str, str]:
    return {
        "hp": "mainhp",
        "atk": "mainatk",
        "def": "maindef",
        "energyregen": "mainenergyregen",
        "critrate": "maincritrate",
        "critdmg": "maincritdmg",
        "critdamage": "maincritdmg",
    }


def main() -> None:
    db = json.loads((ROOT / "game_text_db.json").read_text(encoding="utf-8"))
    lines = ["HP", "ATK", ") DEF", "Energy Regen", "-Crit.Rate", "Crit. DMG"]
    alias = stat_alias_map()
    print("list_mode:", is_list_mode(lines))
    for line in lines:
        cleaned = clean_line(line)
        key = normalize_en(cleaned)
        key = alias.get(key, key)
        match = db.get(key, {}).get("matches", [{}])[0]
        print(f"{line!r} -> {key} -> {match.get('text_key')} / {match.get('official_cn')}")


if __name__ == "__main__":
    main()
