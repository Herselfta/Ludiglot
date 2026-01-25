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
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


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
        "critdmgbonus": "maincritdmg",
    }


def main() -> None:
    db_path = Path(__file__).resolve().parents[1] / "game_text_db.json"
    db = json.loads(db_path.read_text(encoding="utf-8"))

    lines_list = [
        "HP",
        "ATK",
        ") DEF",
        "Energy Regen",
        "-Crit.Rate",
        "Crit. DMG",
    ]

    lines_long = [
        "Summon Hyvatia to attack",
        "enemies, dealing Spectro DMG and",
        "granting All-Attribute DMG Bonus",
        "to the next Resonator using Intro",
        "Skill.",
    ]

    print("=== List mode test ===")
    print("list_mode:", is_list_mode(lines_list))
    alias = stat_alias_map()
    for line in lines_list:
        cleaned = clean_line(line)
        key = normalize_en(cleaned)
        key = alias.get(key, key)
        match = db.get(key, {}).get("matches", [{}])[0]
        print(f"{line!r} -> {key} -> {match.get('text_key')} / {match.get('official_cn')}")

    print("\n=== Long text prefix test ===")
    joined = " ".join(lines_long)
    key = normalize_en(joined)
    prefix_hits = [k for k in db.keys() if k.startswith(key)]
    if prefix_hits:
        best = min(prefix_hits, key=len)
        match = db.get(best, {}).get("matches", [{}])[0]
        print("prefix hit:", best)
        print("text_key:", match.get("text_key"))
        print("cn:", match.get("official_cn"))
    else:
        # 回退：用标题前缀测试
        title_key = normalize_en(lines_long[0])
        prefix_hits = [k for k in db.keys() if k.startswith(title_key)]
        best = min(prefix_hits, key=len) if prefix_hits else ""
        match = db.get(best, {}).get("matches", [{}])[0] if best else {}
        print("title prefix hit:", best)
        print("text_key:", match.get("text_key"))
        print("cn:", match.get("official_cn"))


if __name__ == "__main__":
    main()
