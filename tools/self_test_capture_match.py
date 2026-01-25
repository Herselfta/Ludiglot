#!/usr/bin/env python
"""自测：使用日志中的OCR文本验证匹配结果（模拟 capture.png 识别输出）"""

import json
from pathlib import Path

from ludiglot.ui.overlay_window import OverlayWindow


class _Log:
    def emit(self, msg: str) -> None:
        print(msg)


class _Signals:
    log = _Log()


def main() -> None:
    db = json.loads(Path("game_text_db.json").read_text(encoding="utf-8"))

    win = OverlayWindow.__new__(OverlayWindow)
    win.db = db
    win.voice_map = {}
    win.voice_event_index = None
    win.signals = _Signals()

    lines = [
        ("Basic Attack", 0.92),
        (
            "Perform up to 4 consecutive attacks, dealing Aero DMG. Basic Attack Stage 4 inflicts 1 stack of Aero Erosion upon the target hit. - When the first three stages of Ciaccona's Basic Attack are interrupted by dodging, press Basic Attack in time to resume the attack cycle and cast the corresponding Basic Attack stage. - After Basic Attack Stage 4, Ciaccona starts a Solo Concert. If Ciaccona's Basic Attack Stage 4 or Solo Concert ends early (proactively or being interrupted), an Ensemble Sylph is generated.",
            0.92,
        ),
    ]

    result = OverlayWindow._lookup_best(win, lines)

    print("\n=== RESULT ===")
    print("matched_key:", result.get("_matched_key"))
    print("score:", result.get("_score"))
    print("query_key:", result.get("_query_key"))
    print("query_len:", len(result.get("_query_key", "")))
    matches = result.get("matches") or []
    cn = matches[0].get("official_cn") if matches else None
    print("cn:", cn[:100] if cn else None)


if __name__ == "__main__":
    main()
