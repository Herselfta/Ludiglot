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


def main() -> None:
    db = json.loads((ROOT / "game_text_db.json").read_text(encoding="utf-8"))
    lines = [
        "Summon Hyvatia to attack",
        "enemies, dealing Spectro DMG and",
        "granting All-Attribute DMG Bonus",
        "to the next Resonator using Intro",
        "Skill.",
    ]
    joined = " ".join(lines)
    key = normalize_en(joined)
    prefix_hits = [k for k in db.keys() if k.startswith(key)]
    if prefix_hits:
        best = min(prefix_hits, key=len)
    else:
        title_key = normalize_en(lines[0])
        prefix_hits = [k for k in db.keys() if k.startswith(title_key)]
        best = min(prefix_hits, key=len) if prefix_hits else ""
    match = db.get(best, {}).get("matches", [{}])[0] if best else {}
    print("matched_key:", best)
    print("text_key:", match.get("text_key"))
    print("cn:", match.get("official_cn"))


if __name__ == "__main__":
    main()
