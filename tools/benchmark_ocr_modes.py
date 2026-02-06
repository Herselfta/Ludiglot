import argparse
import re
from difflib import SequenceMatcher
from pathlib import Path
import sys

try:
    from PIL import Image
except Exception as exc:
    raise SystemExit("Pillow is required for OCR benchmark: pip install Pillow")

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from ludiglot.core.ocr import OCREngine, group_ocr_lines

DEFAULT_EXPECTED = """Mornye

The New Solar Ceremony is nearly upon us. It's the culmination of
decades of work. Everyone at the Collective is giving their all to
realize it.""".strip()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def score(a: str, b: str) -> float:
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def build_raw_text(box_lines):
    ordered = sorted(box_lines, key=lambda b: (b["box"][0][1], b["box"][0][0]))
    return "\n".join([str(b.get("text", "")).strip() for b in ordered if str(b.get("text", "")).strip()])


def build_grouped_text(box_lines, lang="en"):
    grouped = group_ocr_lines(box_lines, lang=lang)
    return "\n".join([t for t, _ in grouped if t.strip()])


def run_case(name, image_path: Path, input_mode: str, adaptive: bool, refine: bool, line_refine: bool = False, preprocess: bool = False, segment: bool = False, multiscale: bool = False):
    engine = OCREngine(lang="en")
    engine.win_ocr_adaptive = adaptive
    engine.win_ocr_refine = refine
    engine.win_ocr_line_refine = line_refine
    engine.win_ocr_preprocess = preprocess
    engine.win_ocr_segment = segment
    engine.win_ocr_multiscale = multiscale

    box_lines = []
    backend = "windows"
    if input_mode == "path":
        box_lines = engine.recognize_with_boxes(image_path)
        backend = engine.last_backend or "windows"
    elif input_mode == "png-bytes":
        data = image_path.read_bytes()
        box_lines = engine._windows_ocr_recognize_from_bytes(data)
    elif input_mode == "raw-bgra":
        img = Image.open(image_path).convert("RGBA")
        raw = img.tobytes("raw", "BGRA")
        box_lines = engine._windows_ocr_recognize_from_bytes((raw, img.width, img.height))
    else:
        raise ValueError(f"Unknown input_mode: {input_mode}")

    raw_text = build_raw_text(box_lines) if box_lines else ""
    grouped_text = build_grouped_text(box_lines) if box_lines else ""
    return {
        "name": name,
        "backend": backend,
        "boxes": len(box_lines),
        "raw_text": raw_text,
        "grouped_text": grouped_text,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default=str(project_root / "cache" / "capture.png"))
    parser.add_argument("--expected", default=None, help="Expected text file path (utf-8)")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        raise SystemExit(f"Image not found: {image_path}")

    if args.expected:
        expected = Path(args.expected).read_text(encoding="utf-8").strip()
    else:
        expected = DEFAULT_EXPECTED

    cases = [
        ("winocr_path_current", "path", True, True),
        ("winocr_path_no_adaptive", "path", False, True),
        ("winocr_path_no_refine", "path", True, False),
        ("winocr_path_pure", "path", False, False),
        ("winocr_raw_bgra_current", "raw-bgra", True, True),
        ("winocr_raw_bgra_pure", "raw-bgra", False, False),
    ]

    # Line-level refine variants
    line_cases = [
        ("winocr_path_current_line", "path", True, True),
        ("winocr_path_pure_line", "path", False, False),
    ]

    preprocess_cases = [
        ("winocr_path_current_pre", "path", True, True),
        ("winocr_path_pure_pre", "path", False, False),
    ]
    segment_cases = [
        ("winocr_path_current_seg", "path", True, True),
        ("winocr_path_pure_seg", "path", False, False),
    ]
    multiscale_cases = [
        ("winocr_path_current_multi", "path", True, True),
        ("winocr_path_pure_multi", "path", False, False),
    ]

    results = []
    for name, mode, adaptive, refine in cases:
        res = run_case(name, image_path, mode, adaptive, refine)
        res["raw_score"] = score(res["raw_text"], expected)
        res["group_score"] = score(res["grouped_text"], expected)
        results.append(res)

    for name, mode, adaptive, refine in line_cases:
        res = run_case(name, image_path, mode, adaptive, refine, True)
        res["line_refine"] = True
        res["raw_score"] = score(res["raw_text"], expected)
        res["group_score"] = score(res["grouped_text"], expected)
        results.append(res)

    for name, mode, adaptive, refine in preprocess_cases:
        res = run_case(name, image_path, mode, adaptive, refine, False, True)
        res["preprocess"] = True
        res["raw_score"] = score(res["raw_text"], expected)
        res["group_score"] = score(res["grouped_text"], expected)
        results.append(res)

    for name, mode, adaptive, refine in segment_cases:
        res = run_case(name, image_path, mode, adaptive, refine, False, False, True)
        res["segment"] = True
        res["raw_score"] = score(res["raw_text"], expected)
        res["group_score"] = score(res["grouped_text"], expected)
        results.append(res)

    for name, mode, adaptive, refine in multiscale_cases:
        res = run_case(name, image_path, mode, adaptive, refine, False, False, False, True)
        res["multiscale"] = True
        res["raw_score"] = score(res["raw_text"], expected)
        res["group_score"] = score(res["grouped_text"], expected)
        results.append(res)

    print("=== OCR Benchmark ===")
    print(f"Image: {image_path}")
    print("Expected (normalized):")
    print(norm(expected))
    print("")

    for res in results:
        print(f"- {res['name']} | backend={res['backend']} | boxes={res['boxes']} | raw={res['raw_score']:.4f} | grouped={res['group_score']:.4f}")

    best = max(results, key=lambda r: (r["group_score"], r["raw_score"]))
    print("\n=== Best (by grouped score) ===")
    print(f"{best['name']} | backend={best['backend']} | boxes={best['boxes']} | raw={best['raw_score']:.4f} | grouped={best['group_score']:.4f}")
    print("\n--- grouped output ---")
    print(best["grouped_text"])
    print("\n--- raw output ---")
    print(best["raw_text"])


if __name__ == "__main__":
    main()
