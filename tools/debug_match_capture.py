from __future__ import annotations

import json
from pathlib import Path

from ludiglot.core.config import load_config
from ludiglot.core.ocr import OCREngine, group_ocr_lines
from ludiglot.core.text_builder import build_text_db, build_text_db_from_root_all, save_text_db
from ludiglot.core.search import FuzzySearcher
from ludiglot.ui.overlay_window import OverlayWindow


def _needs_tesseract(lines: list[tuple[str, float]]) -> bool:
    if len(lines) < 3:
        return False
    for text, conf in lines:
        if conf < 0.35 and len(text) >= 15:
            return True
    low_conf = [conf for _, conf in lines if conf < 0.4]
    if low_conf and (len(low_conf) / len(lines)) >= 0.4:
        return True
    avg_conf = sum(conf for _, conf in lines) / max(len(lines), 1)
    if avg_conf < 0.7:
        return True
    joined = " ".join(text for text, _ in lines)
    if not joined:
        return False
    alpha = sum(ch.isalpha() or ch.isspace() for ch in joined)
    ratio = alpha / max(len(joined), 1)
    return ratio < 0.65


def _ensure_db(config) -> dict:
    if config.db_path.exists():
        return json.loads(config.db_path.read_text(encoding="utf-8"))
    if config.data_root:
        db = build_text_db_from_root_all(config.data_root)
    else:
        db = build_text_db(config.en_json, config.zh_json)
    save_text_db(db, config.db_path)
    return db


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config_path = project_root / "config" / "settings.json"
    config = load_config(config_path)
    config.hotkey_capture = ""
    config.hotkey_toggle = None
    config.play_audio = False
    config.scan_audio_on_start = False

    db = _ensure_db(config)
    matcher = _build_matcher(db)

    engine = OCREngine(
        lang=config.ocr_lang,
        use_gpu=config.ocr_gpu,
        mode=config.ocr_mode,
    )
    engine.initialize()

    image_path = config.image_path
    if not image_path.exists():
        print(f"[ERROR] capture.png 不存在: {image_path}")
        return

    print(f"[CAPTURE] OCR 目标: {image_path}")
    print(f"[OCR] 配置模式: {config.ocr_mode}, 后端: {config.ocr_backend}")
    print("=" * 60)
    
    # 第一次OCR尝试 - 使用自动后端选择
    box_lines = engine.recognize_with_boxes(image_path)
    lines = group_ocr_lines(box_lines)
    backend_used = getattr(engine, "last_backend", None) or "unknown"
    
    print("=" * 60)
    print(f"[OCR] 实际使用后端: {backend_used}")
    print(f"[OCR] 识别到 {len(lines)} 行文本")
    
    # 根据配置决定是否尝试 Tesseract 兜底
    if config.ocr_backend == "auto" and _needs_tesseract(lines) and backend_used != "tesseract":
        print("[OCR] 质量检查: 需要尝试 Tesseract 兜底")
        box_lines_t = engine.recognize_with_boxes(image_path, prefer_tesseract=True)
        lines_t = group_ocr_lines(box_lines_t)
        if len(lines_t) > len(lines) or sum(c for _, c in lines_t) > sum(c for _, c in lines):
            lines = lines_t
            backend_used = "tesseract"
            print(f"[OCR] 使用 Tesseract 结果 ({len(lines)} 行)")
    
    print("-" * 60)
    print("[OCR] 识别结果:")
    for idx, (text, conf) in enumerate(lines, 1):
        print(f"  {idx}. {text} (conf={conf:.3f})")
    print("=" * 60)

    result = matcher._lookup_best(lines)
    if not result:
        print("[RESULT] 未匹配到结果")
        return
    if result.get("_multi"):
        print("[RESULT] multi")
        for item in result.get("items", []):
            print(f"  - {item.get('ocr')} -> {item.get('text_key')} (score={item.get('score')})")
        return
    matches = result.get("matches") or []
    match = matches[0] if matches else {}
    print(f"[RESULT] text_key={match.get('text_key')} score={result.get('_score')} query={result.get('_query_key')}")


class _DummyLog:
    def emit(self, message: str) -> None:
        print(message)


class _DummySignals:
    def __init__(self) -> None:
        self.log = _DummyLog()


def _build_matcher(db: dict) -> OverlayWindow:
    matcher = OverlayWindow.__new__(OverlayWindow)
    matcher.db = db
    matcher.searcher = FuzzySearcher()
    matcher.signals = _DummySignals()
    return matcher

if __name__ == "__main__":
    main()
