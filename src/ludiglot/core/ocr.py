from __future__ import annotations

import base64
import io
import json
import os
import shutil
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

from ludiglot.infrastructure.proxy_setup import setup_system_proxy
setup_system_proxy()
from typing import Any, Callable, Dict, List, Tuple, Union

import re
import inspect
try:
    from PIL import Image, ImageOps, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    Image = None
    ImageOps = None
    ImageFilter = None

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    np = None
    HAS_NUMPY = False

PaddleOCR = None
GLM_OCR_OUTPUT_SCHEMA = (
    '{"lines":["<line1>","<line2>"]}'
)

DEFAULT_GLM_OCR_PROMPT = (
    "You are an OCR engine. Extract all readable text from the image.\n"
    "Rules:\n"
    "- Return only the recognized text.\n"
    "- Preserve line breaks as in the image.\n"
    "- Do not add any commentary or formatting.\n"
    "Output ONLY the following JSON, do not include any other text:\n"
    + GLM_OCR_OUTPUT_SCHEMA
    + "\n"
)
DEFAULT_GLM_OCR_TIMEOUT = 30.0
DEFAULT_GLM_OCR_MAX_TOKENS = 128


class OCREngine:
    """封装多后端 OCR。"""

    def __init__(
        self,
        lang: str = "en",
        use_gpu: bool = False,
        mode: str | None = None,
        det: bool = True,
        rec: bool = True,
        cls: bool = False,
        glm_endpoint: str | None = None,
        glm_ollama_model: str | None = None,
        glm_timeout: float | None = None,
        glm_max_tokens: int | None = None,
        allow_paddle: bool = True,
    ) -> None:
        self.lang = lang
        self.mode = (mode or ("gpu" if use_gpu else "cpu")).lower()
        self.use_gpu = use_gpu
        self.det = det
        self.rec = rec
        self.cls = cls
        self.ready = False
        self._ocr = None
        self._supports_cls = True
        self._pytesseract = None
        self.active_gpu = False
        self._windows_ocr = None
        self._windows_ready = False
        self.last_backend: str | None = None
        # Windows OCR tuning toggles (used for benchmarking / ablation)
        self.win_ocr_adaptive = True
        self.win_ocr_refine = True
        self.win_ocr_line_refine = False
        self.win_ocr_preprocess = False
        self.win_ocr_segment = False
        self.win_ocr_multiscale = False
        self._words_segmenter = None
        self._words_segmenter_ready = False
        self.allow_paddle = bool(allow_paddle)
        endpoint = glm_endpoint or os.getenv("LUDIGLOT_GLM_OCR_ENDPOINT") or os.getenv("OLLAMA_HOST")
        if endpoint:
            endpoint = str(endpoint).strip()
            if not endpoint.startswith(("http://", "https://")):
                endpoint = f"http://{endpoint}"
            self.glm_endpoint = endpoint.rstrip("/")
        else:
            self.glm_endpoint = None
        ollama_model = glm_ollama_model or os.getenv("LUDIGLOT_GLM_OCR_OLLAMA_MODEL") or os.getenv("LUDIGLOT_GLM_OCR_MODEL") or "glm-ocr:latest"
        self.glm_ollama_model = str(ollama_model)
        timeout_raw = glm_timeout if glm_timeout is not None else os.getenv("LUDIGLOT_GLM_OCR_TIMEOUT")
        try:
            self.glm_timeout = float(timeout_raw) if timeout_raw is not None else DEFAULT_GLM_OCR_TIMEOUT
        except Exception:
            self.glm_timeout = DEFAULT_GLM_OCR_TIMEOUT
        max_tokens_raw = glm_max_tokens if glm_max_tokens is not None else os.getenv("LUDIGLOT_GLM_OCR_MAX_TOKENS")
        try:
            self.glm_max_tokens = int(max_tokens_raw) if max_tokens_raw is not None else DEFAULT_GLM_OCR_MAX_TOKENS
        except Exception:
            self.glm_max_tokens = DEFAULT_GLM_OCR_MAX_TOKENS

        self.glm_prompt = DEFAULT_GLM_OCR_PROMPT
        self._glm_ollama_last_error = None
        self._log_callback: Callable[[str], None] | None = None
        self._status_callback: Callable[[str], None] | None = None
        self._prewarm_lock = threading.Lock()
        self._prewarm_started: set[str] = set()

    def set_logger(
        self,
        log_callback: Callable[[str], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._log_callback = log_callback
        self._status_callback = status_callback

    def _atomic_write(self, text: str) -> None:
        if not text:
            return
        msg = text if text.endswith("\n") else text + "\n"
        
        # If no callback (CLI), write to stdout
        if not self._log_callback:
            try:
                sys.stdout.write(msg)
                sys.stdout.flush()
            except Exception:
                # Best-effort output; ignore stdout write/flush errors
                pass
        
        # Always invoke callbacks if available
        if self._log_callback:
            try:
                self._log_callback(text)
            except Exception:
                # Log callback errors should not interrupt OCR; ignore them
                pass

    def _emit_log(self, message: str) -> None:
        self._atomic_write(message)

    def _emit_status(self, message: str) -> None:
        if not message:
            return
        # Internal status updates for GLM-OCR get the [OCR] prefix in terminal
        if message.startswith("GLM-OCR"):
            self._atomic_write(f"[OCR] {message}")
        
        if self._status_callback:
            try:
                self._status_callback(message)
            except Exception:
                # Status callback errors should not interrupt OCR; ignore them
                pass

    def _format_exc(self, exc: Exception | None) -> str:
        if exc is None:
            return ""
        msg = str(exc)
        if msg:
            return f"{exc.__class__.__name__}: {msg}"
        return exc.__class__.__name__

    def _format_error(self, stage: str, exc: Exception | None = None) -> str:
        detail = self._format_exc(exc)
        return f"{stage}: {detail}" if detail else stage

    def _shorten_error(self, text: str | None, limit: int = 180) -> str | None:
        if not text:
            return None
        cleaned = str(text).replace("\n", " ").strip()
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: max(0, limit - 1)] + "…"

    def _reset_glm_ollama_error(self) -> None:
        self._glm_ollama_last_error = None

    def _set_glm_ollama_error(self, stage: str, exc: Exception | None = None) -> None:
        self._glm_ollama_last_error = self._format_error(stage, exc)

    def set_mode(self, mode: str) -> None:
        self.mode = mode.lower()
        self.ready = False
        self._ocr = None

    def _normalize_backend_key(self, backend: str | None) -> str:
        key = str(backend or "auto").strip().lower().replace("-", "_")
        if key == "glm_ocr":
            key = "glm"
        return key

    def _warmup_glm_ollama(self) -> bool:
        self._reset_glm_ollama_error()
        if not self.glm_endpoint:
            self._set_glm_ollama_error("Ollama 地址未设置")
            return False
        url = f"{self.glm_endpoint}/api/tags"
        req = urllib.request.Request(
            url,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=min(self.glm_timeout, 5.0)) as resp:
                ok = 200 <= getattr(resp, "status", 200) < 300
                if not ok:
                    self._set_glm_ollama_error("预热失败")
                return ok
        except Exception as exc:
            self._emit_log(f"[OCR] GLM-OCR (Ollama) 预热失败：{exc}")
            self._set_glm_ollama_error("预热失败", exc)
            return False

    def prewarm(self, backend: str | None = None, async_: bool = True) -> None:
        key = self._normalize_backend_key(backend)
        if key == "glm_ollama" and not self.glm_endpoint:
            return
        with self._prewarm_lock:
            if key in self._prewarm_started:
                return
            self._prewarm_started.add(key)

        def _worker() -> None:
            if key in {"glm", "glm_ollama"}:
                self._emit_log("[OCR] 预热 GLM-OCR (Ollama)...")
                ok = self._warmup_glm_ollama()
                if ok:
                    self._emit_log("[OCR] GLM-OCR (Ollama) 预热完成")
                else:
                    reason = self._shorten_error(self._glm_ollama_last_error)
                    if reason:
                        self._emit_log(f"[OCR] GLM-OCR (Ollama) 预热失败：{reason}")
                    else:
                        self._emit_log("[OCR] GLM-OCR (Ollama) 预热失败")
            elif key == "paddle":
                self.initialize(force_paddle=True, allow_paddle=True)
            elif key == "auto":
                self.initialize(allow_paddle=self.allow_paddle)

        if async_:
            threading.Thread(target=_worker, daemon=True).start()
        else:
            _worker()

    def _detect_paddle_cls_support(self, ocr_obj) -> bool:
        try:
            predict = getattr(ocr_obj, "predict", None)
            if predict is not None:
                sig = inspect.signature(predict)
                return "cls" in sig.parameters
        except Exception:
            return False

        try:
            ocr_fn = getattr(ocr_obj, "ocr", None)
            if ocr_fn is None:
                return False
            sig = inspect.signature(ocr_fn)
            return "cls" in sig.parameters
        except Exception:
            return False

    def _paddle_extract_lines(self, result) -> List[Dict[str, object]]:
        lines: List[Dict[str, object]] = []
        if not result:
            return lines

        if isinstance(result, list) and result and isinstance(result[0], dict):
            for page in result:
                texts = page.get("rec_texts")
                if texts is None:
                    texts = []
                scores = page.get("rec_scores")
                if scores is None:
                    scores = []
                polys = page.get("rec_polys")
                if polys is None:
                    polys = page.get("dt_polys")
                if polys is None:
                    polys = []
                rec_boxes = page.get("rec_boxes")
                if rec_boxes is None:
                    rec_boxes = []

                for i, text in enumerate(texts):
                    conf = float(scores[i]) if i < len(scores) else 0.0
                    box = None
                    if i < len(polys):
                        try:
                            poly = polys[i]
                            box = [[int(p[0]), int(p[1])] for p in poly]
                        except Exception:
                            box = None
                    if box is None and i < len(rec_boxes):
                        try:
                            rb = rec_boxes[i]
                            if len(rb) >= 4 and isinstance(rb[0], (list, tuple)):
                                box = [[int(p[0]), int(p[1])] for p in rb]
                            elif len(rb) >= 4:
                                x1, y1, x2, y2 = map(int, rb[:4])
                                box = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
                        except Exception:
                            box = None
                    if box is None:
                        box = [[0, 0], [0, 0], [0, 0], [0, 0]]
                    lines.append({"text": str(text), "conf": conf, "box": box})
            return lines

        for block in result:
            for item in block:
                box = item[0]
                text = item[1][0]
                conf = float(item[1][1])
                lines.append({"text": text, "conf": conf, "box": box})
        return lines

    def initialize(self, force_paddle: bool = False, allow_paddle: bool | None = None) -> None:
        """初始化 OCR 引擎。

        策略：
        1. 总是初始化 Windows OCR（如果可用）。
        2. 只有在明确指定paddle模式或auto模式下Windows OCR不可用时才加载PaddleOCR。
        """
        if allow_paddle is None:
            allow_paddle = self.allow_paddle
        # 1. 初始化 Windows OCR (轻量级)
        self._init_windows_ocr()

        if not allow_paddle and not force_paddle:
            self.ready = True
            return

        # 2. 检查是否需要加载 PaddleOCR
        # 如果是 winrt 模式，或 auto 模式下 Windows OCR 可用，则无需加载 Paddle
        if (not force_paddle) and self.mode == "winrt":
             print("[OCR] 模式=winrt，无需加载 PaddleOCR")
             return

        if (not force_paddle) and self.mode == "auto" and self._windows_ocr is not None:
             print("[OCR] 模式=auto 且 Windows OCR 可用，无需加载 PaddleOCR")
             return

        if (not force_paddle) and self.mode == "tesseract":
             print("[OCR] 使用 Tesseract，无需加载 PaddleOCR")
             return

        # 3. 准备加载 PaddleOCR（仅在明确需要时）
        global PaddleOCR
        
        os.environ.setdefault("FLAGS_enable_pir_api", "0")
        os.environ.setdefault("FLAGS_use_pir_api", "0")
        os.environ.setdefault("FLAGS_enable_pir_in_executor", "0")
        os.environ.setdefault("FLAGS_use_pir", "0")
        os.environ.setdefault("FLAGS_enable_new_ir", "0")
        os.environ.setdefault("FLAGS_use_new_executor", "0")
        os.environ.setdefault("FLAGS_use_mkldnn", "0")
        os.environ.setdefault("FLAGS_use_onednn", "0")
        os.environ.setdefault("PADDLE_ENABLE_PIR", "0")

        if PaddleOCR is None:
            try:
                from paddleocr import PaddleOCR as _PaddleOCR
                PaddleOCR = _PaddleOCR
            except ImportError:
                if self.mode == "paddle":
                    raise RuntimeError(
                        "PaddleOCR 未安装，请先完成安装: pip install ludiglot[paddle]"
                    )
                else:
                    print("[OCR] PaddleOCR 未安装，跳过加载。")
                    return
            except Exception as exc:
                print(f"[OCR] 加载 PaddleOCR 失败: {exc}")
                return

        try:
            import paddle

            paddle.set_flags(
                {
                    "FLAGS_enable_pir_api": 0,
                    "FLAGS_use_pir_api": 0,
                    "FLAGS_enable_pir_in_executor": 0,
                    "FLAGS_use_pir": 0,
                    "FLAGS_enable_new_ir": 0,
                    "FLAGS_use_new_executor": 0,
                    "FLAGS_use_mkldnn": 0,
                    "FLAGS_use_onednn": 0,
                }
            )
        except Exception:
            pass
        if self.mode == "auto":
            gpu_candidates = [True, False]
        elif self.mode == "gpu":
            gpu_candidates = [True]
        else:
            gpu_candidates = [False]

        base_candidates = []
        for use_gpu in gpu_candidates:
            base_candidates.append({"use_gpu": use_gpu, "lang": self.lang})
        base_candidates.extend([
            {"lang": self.lang},
            {},
        ])
        extra_candidates = [
            {"det": self.det, "rec": self.rec, "cls": self.cls},
            {"det": self.det, "rec": self.rec},
            {"det": self.det},
            {},
        ]
        last_error: Exception | None = None
        for base_kwargs in base_candidates:
            for extra in extra_candidates:
                try:
                    self._ocr = PaddleOCR(**base_kwargs, **extra)
                    self._supports_cls = self._detect_paddle_cls_support(self._ocr)
                    self.active_gpu = bool(base_kwargs.get("use_gpu"))
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    continue
            if self._ocr is not None:
                break
        if self._ocr is None and last_error is not None:
            raise last_error
        self.ready = True

    def _init_windows_ocr(self) -> None:
        """初始化 Windows 原生 OCR 引擎。"""
        if self._windows_ready:
            return
        
        # 尝试导入 WinRT 模块
        try:
            from winrt.windows.globalization import Language
            from winrt.windows.media.ocr import OcrEngine
        except ImportError as e:
            self._emit_log(f"[OCR] Windows OCR 不可用：WinRT 依赖缺失 ({e.__class__.__name__})")
            self._emit_log("[OCR] 提示：可通过 'pip install winrt-Windows.Media.Ocr winrt-Windows.Globalization' 安装")
            self._windows_ready = True
            self._windows_ocr = None
            return
        except Exception as e:
            self._emit_log(f"[OCR] Windows OCR 导入失败：{e.__class__.__name__}: {e}")
            self._windows_ready = True
            self._windows_ocr = None
            return
        
        # 检查可用的语言包
        try:
            available_langs = OcrEngine.available_recognizer_languages
            available_lang_codes = [lang.language_tag for lang in available_langs]
            self._emit_log(f"[OCR] Windows OCR 可用语言包: {', '.join(available_lang_codes) if available_lang_codes else '无'}")
        except Exception as e:
            self._emit_log(f"[OCR] 无法检查语言包：{e}")
            available_lang_codes = []
        
        # 尝试创建 OCR 引擎实例
        try:
            self._emit_log(f"[OCR Config] Requesting Lang: {self.lang}")
            if self.lang.startswith("en"):
                # Try specific US English first
                lang = Language("en-US")
                if not OcrEngine.is_language_supported(lang):
                     self._emit_log("[OCR Config] en-US not supported, checking others...")
                
                self._windows_ocr = OcrEngine.try_create_from_language(lang)
                if self._windows_ocr is None:
                    # Fallback to en-GB if en-US missing (common in some regions)
                    self._emit_log("[OCR] Windows OCR: en-US failed, trying en-GB")
                    lang_gb = Language("en-GB")
                    self._windows_ocr = OcrEngine.try_create_from_language(lang_gb)

                if self._windows_ocr is None:
                    self._emit_log("[OCR] Windows OCR：en-US 语言包未安装")
                    if "en-US" not in available_lang_codes and "en" not in available_lang_codes:
                        self._emit_log("[OCR] 提示：请安装英语语言包")
                        self._emit_log("[OCR]   设置 -> 时间和语言 -> 语言 -> 添加语言 -> English (United States)")
                    self._emit_log("[OCR] 尝试使用系统默认语言包...")
                    self._windows_ocr = OcrEngine.try_create_from_user_profile_languages()
            elif self.lang.startswith("zh"):
                lang = Language("zh-CN")
                self._windows_ocr = OcrEngine.try_create_from_language(lang)
                if self._windows_ocr is None:
                    self._emit_log("[OCR] Windows OCR：zh-CN 语言包未安装")
                    if "zh-CN" not in available_lang_codes and "zh" not in available_lang_codes:
                        self._emit_log("[OCR] 提示：请安装中文语言包")
                        self._emit_log("[OCR]   设置 -> 时间和语言 -> 语言 -> 添加语言 -> 中文(简体，中国)")
                    self._emit_log("[OCR] 尝试使用系统默认语言包...")
                    self._windows_ocr = OcrEngine.try_create_from_user_profile_languages()
            else:
                self._windows_ocr = OcrEngine.try_create_from_user_profile_languages()
            
            if self._windows_ocr is None:
                self._emit_log("[OCR] Windows OCR 不可用：系统未安装任何 OCR 语言包")
                self._emit_log("[OCR] 请在 Windows 设置中安装语言包：")
                self._emit_log("[OCR]   设置 -> 时间和语言 -> 语言 -> 添加语言")
            else:
                lang_tag = self._windows_ocr.recognizer_language.language_tag if self._windows_ocr.recognizer_language else "unknown"
                self._emit_log(f"[OCR] Windows OCR 初始化成功 (使用语言: {lang_tag})")
        except Exception as e:
            self._emit_log(f"[OCR] Windows OCR 初始化失败：{e.__class__.__name__}: {e}")
            self._windows_ocr = None
        
        self._windows_ready = True

    def _pil_to_png_bytes(self, image: Any) -> bytes | None:
        if not HAS_PIL or Image is None or image is None:
            return None
        try:
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return None

    def _glm_image_to_bytes(self, image_input: Union[str, Path, Any, tuple]) -> bytes | None:
        if isinstance(image_input, (str, Path)):
            try:
                return Path(image_input).read_bytes()
            except Exception:
                return None

        if isinstance(image_input, tuple) and len(image_input) == 3:
            if not HAS_PIL or Image is None:
                return None
            try:
                r_bytes, r_w, r_h = image_input
                img = Image.frombytes("RGBA", (int(r_w), int(r_h)), r_bytes, "raw", "BGRA")
                return self._pil_to_png_bytes(img)
            except Exception:
                return None

        if HAS_NUMPY and np is not None and isinstance(image_input, np.ndarray):
            if not HAS_PIL or Image is None:
                return None
            try:
                if len(image_input.shape) == 3 and image_input.shape[2] == 3:
                    img = Image.fromarray(image_input[:, :, ::-1])
                else:
                    img = Image.fromarray(image_input)
                return self._pil_to_png_bytes(img)
            except Exception:
                return None

        if HAS_PIL and Image is not None and isinstance(image_input, Image.Image):
            return self._pil_to_png_bytes(image_input)

        return None

    def _glm_extract_lines(self, text: str) -> List[str]:
        if not text:
            return []
        cleaned = str(text).strip()
        if not cleaned:
            return []
        try:
            prompt_text = str(self.glm_prompt or "").strip()
        except Exception:
            prompt_text = ""
        if prompt_text and prompt_text in cleaned:
            cleaned = cleaned.rsplit(prompt_text, 1)[-1].strip()

        def _normalize_line(value: str) -> str:
            normalized = re.sub(r"^([-*•]\\s+|\\d+[\\.)]\\s+)", "", value.strip())
            normalized = re.sub(r"\\s+", " ", normalized)
            normalized = normalized.lower()
            normalized = normalized.rstrip(":")
            return normalized

        prompt_lines: list[str] = []
        for line in str(self.glm_prompt).splitlines():
            line = line.strip()
            if not line:
                continue
            line = re.sub(r"^([-*•]\\s+|\\d+[\\.)]\\s+)", "", line).strip()
            if line:
                prompt_lines.append(line)
        prompt_norm = {_normalize_line(line) for line in prompt_lines if line}

        def _strip_image_tokens(value: str) -> str:
            stripped = re.sub(r"<\\|image[^|>]*\\|>", "", value)
            stripped = re.sub(r"<\\|image[^>]*", "", stripped)
            stripped = stripped.replace("<|endoftext|>", "")
            stripped = stripped.replace("<|begin_of_text|>", "")
            stripped = stripped.replace("<|assistant|>", "")
            stripped = stripped.replace("<|user|>", "")
            stripped = stripped.replace("<|system|>", "")
            stripped = stripped.replace("<|bos|>", "")
            stripped = stripped.replace("<|eos|>", "")
            stripped = stripped.replace("<|im_start|>", "")
            stripped = stripped.replace("<|im_end|>", "")
            return stripped.strip()

        def _filter_prompt_lines(lines: list[str]) -> list[str]:
            if not lines:
                return []
            def _is_token_fragment(value: str) -> bool:
                v = value.strip()
                if not v:
                    return True
                if v.startswith("```"):
                    return True
                if re.fullmatch(r"[{}\[\]\s,:-]+", v):
                    return True
                compact = re.sub(r"[\s\[\]{},:]", "", v).strip("\"'").lower()
                if compact == "lines":
                    return True
                if "<|" in v or "|>" in v:
                    if len(v) <= 8:
                        return True
                    if not re.search(r"[A-Za-z0-9]", v):
                        return True
                if all(ch in "<|>-." for ch in v):
                    return True
                return False

            def _is_schema_placeholder(value: str) -> bool:
                v = value.strip()
                if not v:
                    return True
                if re.fullmatch(r"<line\\d+>", v, flags=re.IGNORECASE):
                    return True
                if re.fullmatch(r"<line\\d+", v, flags=re.IGNORECASE):
                    return True
                if v.lower().startswith("<line") and len(v) <= 10:
                    return True
                return False

            def _looks_like_schema_json(value: str) -> bool:
                v = value.strip()
                if not v.startswith("{"):
                    return False
                low = v.lower()
                if "\"lines\"" in low and "<line" in low:
                    return True
                if "'lines'" in low and "<line" in low:
                    return True
                if "lines" in low and "<line" in low and "[" in low and "]" in low:
                    return True
                return False

            def _looks_like_prompt_line(norm_line: str) -> bool:
                if not norm_line:
                    return False
                if norm_line in prompt_norm:
                    return True
                if len(norm_line) >= 12:
                    for p in prompt_norm:
                        if p.startswith(norm_line) or norm_line.startswith(p):
                            return True
                return False

            filtered: list[str] = []
            for line in lines:
                cleaned_line = _strip_image_tokens(str(line))
                if not cleaned_line:
                    continue
                if _is_token_fragment(cleaned_line):
                    continue
                if _is_schema_placeholder(cleaned_line):
                    continue
                if _looks_like_schema_json(cleaned_line):
                    continue
                norm = _normalize_line(cleaned_line)
                if _looks_like_prompt_line(norm):
                    continue
                filtered.append(cleaned_line)
            return filtered

        def _split_text_value(value: str) -> list[str]:
            parts = []
            raw_value = str(value)
            # normalize escaped newlines when JSON parsing fails or returns raw strings
            raw_value = raw_value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
            for seg in raw_value.splitlines():
                seg = seg.strip()
                if seg:
                    parts.append(seg)
            return parts

        def _extract_from_obj(obj: object) -> list[str]:
            out: list[str] = []
            if isinstance(obj, dict):
                if isinstance(obj.get("lines"), list):
                    for item in obj.get("lines", []):
                        if isinstance(item, str):
                            out.extend(_split_text_value(item))
                        elif isinstance(item, dict) and item.get("text"):
                            out.extend(_split_text_value(item.get("text")))
                elif obj.get("text"):
                    out.extend(_split_text_value(obj.get("text")))
            elif isinstance(obj, list):
                for item in obj:
                    if isinstance(item, str):
                        out.extend(_split_text_value(item))
                    elif isinstance(item, dict) and item.get("text"):
                        out.extend(_split_text_value(item.get("text")))
            return out

        def _parse_json_payload(raw: str) -> list[str]:
            if not raw:
                return []
            raw_str = str(raw).strip()
            if not raw_str:
                return []

            candidates: list[list[str]] = []

            def _score(lines: list[str]) -> tuple[int, int]:
                return (len(lines), sum(len(x) for x in lines))

            def _push(lines: list[str]) -> None:
                if not lines:
                    return
                filtered = _filter_prompt_lines(lines)
                if filtered:
                    candidates.append(filtered)

            def _unwrap_obj(obj: object) -> object:
                if isinstance(obj, str):
                    inner = obj.strip()
                    if inner.startswith("{") or inner.startswith("["):
                        try:
                            return json.loads(inner)
                        except Exception:
                            return obj
                return obj

            def _try_obj(obj: object) -> None:
                obj = _unwrap_obj(obj)
                extracted = _extract_from_obj(obj)
                if extracted:
                    _push(extracted)

            try:
                _try_obj(json.loads(raw_str))
            except Exception:
                # Attempt full JSON parse; if this fails, continue with incremental decoding
                pass

            decoder = json.JSONDecoder()
            idx = 0
            length = len(raw_str)
            while idx < length:
                next_brace = raw_str.find("{", idx)
                next_bracket = raw_str.find("[", idx)
                if next_brace == -1 and next_bracket == -1:
                    break
                if next_brace == -1:
                    start = next_bracket
                elif next_bracket == -1:
                    start = next_brace
                else:
                    start = min(next_brace, next_bracket)
                try:
                    obj, end = decoder.raw_decode(raw_str[start:])
                    _try_obj(obj)
                    idx = start + (end if end > 0 else 1)
                except Exception:
                    idx = start + 1
            # line-level JSON
            for line in raw_str.splitlines():
                line = line.strip()
                if not line:
                    continue
                if not (line.startswith("{") and ("\"lines\"" in line or "\"text\"" in line or "'lines'" in line or "'text'" in line)):
                    continue
                try:
                    _try_obj(json.loads(line))
                except Exception:
                    continue
            # try unescape JSON string content (e.g., \"lines\": ...)
            if "\\\"" in raw_str and ("lines" in raw_str.lower() or "text" in raw_str.lower()):
                try:
                    unescaped = raw_str.encode("utf-8", "backslashreplace").decode("unicode_escape")
                except Exception:
                    unescaped = raw_str.replace("\\\"", "\"").replace("\\\\", "\\")
                if unescaped and unescaped != raw_str:
                    try:
                        _try_obj(json.loads(unescaped))
                    except Exception:
                        # Attempt JSON parse on unescaped payload; if this fails, continue with regex extraction
                        pass
                    # try regex extraction on unescaped payload
                    raw_str = unescaped
            # regex fallback for malformed JSON (e.g., unescaped newlines in strings)
            low = raw_str.lower()
            if "\"lines\"" in low or "'lines'" in low:
                match_body = None
                m = re.search(r"[\"']lines[\"']\s*:\s*\[(.*?)]", raw_str, flags=re.S)
                if m:
                    match_body = m.group(1)
                target = match_body if match_body is not None else raw_str
                matches = re.findall(r"\"((?:\\.|[^\"\\])*)\"", target, flags=re.S)
                if not matches:
                    matches = re.findall(r"'((?:\\.|[^'\\])*)'", target, flags=re.S)
                if matches:
                    out: list[str] = []
                    for m in matches:
                        if m.lower() in ("lines", "text"):
                            continue
                        try:
                            # unescape JSON string content
                            decoded = json.loads(f"\"{m.replace('\"', '\\\"')}\"")
                        except Exception:
                            decoded = m
                        out.extend(_split_text_value(decoded))
                    _push(out)
            if candidates:
                candidates.sort(key=_score, reverse=True)
                return candidates[0]
            return []

        parsed_lines = _parse_json_payload(cleaned)
        if parsed_lines:
            return parsed_lines

        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        cleaned_lines: list[str] = []
        for line in lines:
            normalized = re.sub(r"^([-*•]\s+|\d+[.)]\s+)", "", line).strip()
            if normalized:
                cleaned_lines.append(normalized)
        cleaned_lines = _filter_prompt_lines(cleaned_lines)
        if cleaned_lines and len(cleaned_lines) == 1:
            candidate = cleaned_lines[0].strip()
            if candidate.startswith("{") and ("\"lines\"" in candidate or "\"text\"" in candidate):
                parsed_again = _parse_json_payload(candidate)
                if parsed_again:
                    return parsed_again
        return cleaned_lines

    def _glm_build_boxes(self, lines: List[str]) -> List[Dict[str, object]]:
        if not lines:
            return []
        box_lines: List[Dict[str, object]] = []
        y_step = 80
        box_h = 40
        box_w = 1000
        for idx, text in enumerate(lines):
            y1 = idx * y_step
            y2 = y1 + box_h
            box = [[0, y1], [box_w, y1], [box_w, y2], [0, y2]]
            box_lines.append({"text": text, "conf": 0.85, "box": box})
        return box_lines

    def _glm_ollama_recognize_boxes(self, image_input: Union[str, Path, Any, tuple]) -> List[Dict[str, object]]:
        self._reset_glm_ollama_error()
        if not self.glm_endpoint:
            self._set_glm_ollama_error("Ollama 地址未设置")
            return []
        image_bytes = self._glm_image_to_bytes(image_input)
        if not image_bytes:
            print("[OCR] GLM-OCR 输入转换失败")
            self._set_glm_ollama_error("输入转换失败")
            return []

        payload = {
            "model": self.glm_ollama_model,
            "prompt": self.glm_prompt,
            "images": [base64.b64encode(image_bytes).decode("ascii")],
            "stream": False,
        }
        url = f"{self.glm_endpoint}/api/generate"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.glm_timeout) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
        except urllib.error.URLError as exc:
            print(f"[OCR] GLM-OCR 请求失败：{exc}")
            self._set_glm_ollama_error("请求失败", exc)
            return []
        except Exception as exc:
            print(f"[OCR] GLM-OCR 请求失败：{exc}")
            self._set_glm_ollama_error("请求失败", exc)
            return []

        response_obj = None
        try:
            response_obj = json.loads(raw)
        except Exception:
            for line in raw.splitlines():
                try:
                    response_obj = json.loads(line)
                    break
                except Exception:
                    continue

        if isinstance(response_obj, dict):
            if response_obj.get("error"):
                self._emit_log(f"[OCR] GLM-OCR 错误：{response_obj.get('error')}")
                self._set_glm_ollama_error("响应错误", Exception(str(response_obj.get("error"))))
                return []
            text = response_obj.get("response") or response_obj.get("message") or ""
        else:
            text = raw

        lines = self._glm_extract_lines(text)
        if not lines:
            self._set_glm_ollama_error("输出解析为空")
            return []
        return self._glm_build_boxes(lines)

    def _glm_ocr_recognize_boxes(self, image_input: Union[str, Path, Any, tuple]) -> List[Dict[str, object]]:
        return self._glm_ollama_recognize_boxes(image_input)

    def _windows_ocr_recognize_boxes(self, image_path: str | Path) -> List[Dict[str, object]]:
        """使用 Windows 原生 OCR 识别图片中的文本。
        
        注意：WinRT 异步操作在GUI线程（STA）中可能失败，因此在单独线程中执行。
        """
        # 读取文件内容直接传给字节流处理方法
        try:
            data = Path(image_path).read_bytes()
            return self._windows_ocr_recognize_from_bytes(data)
        except Exception as e:
            self._emit_log(f"[OCR] 读取文件失败：{e}")
            return []

    def _preprocess_windows_input(self, image_input: Union[str, Path, Any, tuple]) -> bytes | None:
        """轻量预处理：灰度 + autocontrast，输出 PNG bytes."""
        if not HAS_PIL or Image is None:
            return None
        try:
            pil_img = None
            if isinstance(image_input, (str, Path)):
                pil_img = Image.open(str(image_input))
            elif isinstance(image_input, tuple) and len(image_input) == 3:
                r_bytes, r_w, r_h = image_input
                pil_img = Image.frombytes("RGBA", (int(r_w), int(r_h)), r_bytes, "raw", "BGRA")
            elif isinstance(image_input, Image.Image):
                pil_img = image_input
            else:
                return None

            if pil_img.mode != "L":
                pil_img = pil_img.convert("L")
            try:
                from PIL import ImageOps
                pil_img = ImageOps.autocontrast(pil_img)
            except Exception:
                # Autocontrast is an optional enhancement; if it fails, continue with the original image
                pass
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return None

    def _get_words_segmenter(self):
        if self._words_segmenter_ready:
            return self._words_segmenter
        self._words_segmenter_ready = True
        try:
            from winrt.windows.data.text import WordsSegmenter
            lang = "en-US" if str(self.lang).startswith("en") else str(self.lang)
            self._words_segmenter = WordsSegmenter(lang)
        except Exception as e:
            self._emit_log(f"[OCR] WordsSegmenter unavailable: {e.__class__.__name__}: {e}")
            self._words_segmenter = None
        return self._words_segmenter

    def _segment_with_words_segmenter(self, text: str) -> str:
        segmenter = self._get_words_segmenter()
        if not segmenter:
            return text
        try:
            tokens = list(segmenter.get_tokens(text))
        except Exception:
            return text
        if not tokens:
            return text
        parts: list[str] = []
        for tok in tokens:
            t = getattr(tok, "text", "") or ""
            if not t:
                continue
            if not parts:
                parts.append(t)
                continue
            prev = parts[-1]
            if prev and prev[-1].isalnum() and t[0].isalnum():
                parts.append(" " + t)
            else:
                parts.append(t)
        return "".join(parts).strip()


    def _parse_winrt_result(self, result) -> List[Dict[str, object]]:
        lines_list = []
        if not result or not getattr(result, "lines", None):
            return lines_list
        
        for line in result.lines:
            text = getattr(line, "text", "") or ""
            if not text.strip():
                continue
            
            words = getattr(line, "words", None)
            if not words or len(list(words)) == 0:
                # Fallback if no words but text exists (rare)
                box = [[0, 0], [100, 0], [100, 30], [0, 30]]
                lines_list.append({"text": text.strip(), "conf": 0.92, "box": box})
                continue
            
            word_list = []
            for word in words:
                w_text = getattr(word, "text", "").strip()
                rect = getattr(word, "bounding_rect", None)
                if not w_text or not rect:
                    continue
                word_list.append({
                    "text": w_text,
                    "x": rect.x,
                    "y": rect.y,
                    "width": rect.width,
                    "height": rect.height
                })
            
            if not word_list:
                continue

            # 行内分组逻辑
            groups = []
            current_group = [word_list[0]]
            for i in range(1, len(word_list)):
                prev = word_list[i-1]
                curr = word_list[i]
                gap = curr["x"] - (prev["x"] + prev["width"])
                
                # 文档建议：基于字符高度动态调整阈值
                threshold = max(50, curr["height"] * 2.5)
                if gap > threshold:
                    groups.append(current_group)
                    current_group = [curr]
                else:
                    current_group.append(curr)
            groups.append(current_group)
            
            for group in groups:
                g_text = " ".join([w["text"] for w in group])
                min_x = min(w["x"] for w in group)
                min_y = min(w["y"] for w in group)
                max_x = max(w["x"] + w["width"] for w in group)
                max_y = max(w["y"] + w["height"] for w in group)
                box = [[int(min_x), int(min_y)], [int(max_x), int(min_y)], 
                       [int(max_x), int(max_y)], [int(min_x), int(max_y)]]
                lines_list.append({"text": g_text, "conf": 0.92, "box": box})
        
        return lines_list



    def _windows_ocr_recognize_from_bytes(self, image_bytes: bytes) -> List[Dict[str, object]]:
        """使用 Windows OCR 从内存字节流识别文本（避免硬盘读写）。
        
        Args:
            image_bytes: PNG/JPEG 格式的图片字节流
            
        Returns:
            识别结果列表
        """
        self._init_windows_ocr()
        if self._windows_ocr is None:
            return []
        
        result_container = {"lines": [], "error": None}
        
        # 定义质量检测函数
        def _check_quality(lines):
            if not lines: return 0.0
            total_len = 0
            valid_chars = 0
            is_english = self.lang.startswith("en")
            
            for line in lines:
                text = line.get("text", "")
                total_len += len(text)
                for ch in text:
                    is_valid = False
                    # 总是允许常用标点
                    if ch in " .,!?'\":;-()[]":
                        is_valid = True
                    elif is_english:
                        # 英文模式下，要求 ASCII 字符
                        if ch.isascii() and ch.isalnum():
                            is_valid = True
                    else:
                        # 其他语言（如中文），只要是字母数字即可
                        if ch.isalnum():
                            is_valid = True
                    
                    if is_valid:
                        valid_chars += 1
            
            if total_len == 0: return 0.0
            return valid_chars / total_len




        def _ocr_worker():
            # print("[OCR Debug] _ocr_worker started", flush=True)
            try:
                from winrt.windows.storage.streams import InMemoryRandomAccessStream, DataWriter
                from winrt.windows.graphics.imaging import BitmapDecoder, SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode
                # print("[OCR Debug] WinRT imports successful", flush=True)
            except ImportError as e:
                # print(f"[OCR Debug] WinRT ImportError: {e}", flush=True)
                result_container["error"] = "WinRT模块导入失败"
                return
            except Exception as e:
                # print(f"[OCR Debug] WinRT Import Exception: {e}", flush=True)
                result_container["error"] = f"模块导入错误 - {e.__class__.__name__}"
                return

            def _ensure_bgra8(bmp):
                """Ensure bitmap is Bgra8 for optimal OCR performance on screenshots."""
                try:
                    target_format = BitmapPixelFormat.BGRA8
                    if bmp.bitmap_pixel_format != target_format:
                         # Use 2-argument convert (source, format) to avoid invalid parameter count
                         return SoftwareBitmap.convert(bmp, target_format)
                except Exception as e:
                    print(f"[OCR] _ensure_bgra8 warning: {e}")
                return bmp

            # _parse_ocr_result moved to self._parse_winrt_result
            
            def _recognize_bytes(data_input, try_invert=True):
                # print("[OCR Debug] _recognize_bytes started", flush=True)
                try:
                    bitmap = None
                    # Support RAW BGRA tuple: (bytes, width, height)
                    if isinstance(data_input, tuple) and len(data_input) == 3:
                         raw_bytes, w, h = data_input
                         try:
                             # Create bitmap from raw bytes via DataWriter (requires copying to WinRT buffer)
                             writer = DataWriter()
                             writer.write_bytes(raw_bytes)
                             buf = writer.detach_buffer()
                             bitmap = None
                             # Some WinRT versions expose different overloads; try a few safe variants.
                             try:
                                 bitmap = SoftwareBitmap.create_copy_from_buffer(
                                     buf, BitmapPixelFormat.BGRA8, w, h, BitmapAlphaMode.PREMULTIPLIED
                                 )
                             except Exception:
                                 try:
                                     bitmap = SoftwareBitmap.create_copy_from_buffer(
                                         buf, BitmapPixelFormat.BGRA8, w, h
                                     )
                                 except Exception:
                                     try:
                                         bitmap = SoftwareBitmap.create_copy_from_buffer(
                                             buf, BitmapPixelFormat.BGRA8, w, h, BitmapAlphaMode.IGNORE
                                         )
                                     except Exception:
                                         bitmap = None
                         except Exception as e:
                             print(f"[OCR] RAW Bitmap creation failed: {e}")
                             bitmap = None
                         if bitmap is None and HAS_PIL and Image is not None:
                             # Fallback: convert raw BGRA to PNG bytes, then decode as encoded image
                             try:
                                 pil_img = Image.frombytes("RGBA", (w, h), raw_bytes, "raw", "BGRA")
                                 buf = io.BytesIO()
                                 pil_img.save(buf, format="PNG")
                                 data_input = buf.getvalue()
                             except Exception as e:
                                 print(f"[OCR] RAW->PNG fallback failed: {e}")
                                 return []
                    else:
                        # Fallback to PNG/Encoded bytes
                        stream = InMemoryRandomAccessStream()
                        writer = DataWriter(stream)
                        writer.write_bytes(data_input)
                        writer.store_async().get()
                        writer.flush_async().get()
                        writer.detach_stream()
                        stream.seek(0)
                        
                        decoder = BitmapDecoder.create_async(stream).get()
                        bitmap = decoder.get_software_bitmap_async().get()
                        # Ensure Bgra8 for general compatibility
                        bitmap = _ensure_bgra8(bitmap)

                    if not self._windows_ocr:
                        return []
                        
                    # Pass 1: Normal Recognition
                    try:
                        result = self._windows_ocr.recognize_async(bitmap).get()
                        lines = self._parse_winrt_result(result)
                    except Exception as e:
                        self._emit_log(f"[OCR] RecognizeAsync failed: {e}")
                        return []
                    
                    # print(f"[OCR Debug] Normal Pass Lines: {len(lines)}", flush=True)
                    
                    # Pass 2: Inverted Logic (Dual-Pass Strategy)
                    # DOCUMENTATION: "OCR 引擎对黑底白字识别能力弱，必须使用双通逻辑"
                    # Always try invert if enabled, then pick the best result.
                    # Pass 2: Inverted Logic (Dual-Pass Strategy with Spatial Fusion)
                    if try_invert and HAS_PIL and Image is not None:
                        try:
                            # 1. Generate Inverted Image
                            # If input is raw tuple logic:
                            pil_img = None
                            if isinstance(data_input, tuple):
                                r_bytes, r_w, r_h = data_input
                                pil_img = Image.frombytes("RGBA", (r_w, r_h), r_bytes, "raw", "BGRA")
                            else:
                                pil_img = Image.open(io.BytesIO(bytes_data))
                                
                            if pil_img.mode == 'RGBA':
                                pil_img = pil_img.convert('RGB')
                                
                            from PIL import ImageOps
                            inv_img = ImageOps.invert(pil_img)
                            
                            # Convert back to raw bytes for efficiency if using raw path
                            # (currently we use PNG bytes directly)
                            buf = io.BytesIO()
                            inv_img.save(buf, format='PNG')
                            inv_bytes = buf.getvalue()
                            
                            # 2. Recognize Inverted
                            inv_lines = _recognize_bytes(inv_bytes, try_invert=False)
                            
                            if not inv_lines:
                                return lines
                                
                            if not lines:
                                return inv_lines
                                
                            # 3. Spatial Fusion (IoU Strategy)
                            fused_lines = list(lines) # Start with normal lines
                            
                            def calc_iou(box1, box2):
                                # box: [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                                b1_x1, b1_y1 = box1[0]
                                b1_x2, b1_y2 = box1[2]
                                b2_x1, b2_y1 = box2[0]
                                b2_x2, b2_y2 = box2[2]
                                
                                xx1 = max(b1_x1, b2_x1)
                                yy1 = max(b1_y1, b2_y1)
                                xx2 = min(b1_x2, b2_x2)
                                yy2 = min(b1_y2, b2_y2)
                                
                                w = max(0.0, xx2 - xx1)
                                h = max(0.0, yy2 - yy1)
                                inter = w * h
                                
                                area1 = (b1_x2 - b1_x1) * (b1_y2 - b1_y1)
                                area2 = (b2_x2 - b2_x1) * (b2_y2 - b2_y1)
                                union = area1 + area2 - inter
                                
                                return inter / union if union > 0 else 0.0

                            # Iterate inverted lines and merge into fused_lines
                            for inv_line in inv_lines:
                                inv_box = inv_line.get('box')
                                if not inv_box: continue
                                
                                best_iou = 0.0
                                match_idx = -1
                                
                                for i, norm_line in enumerate(fused_lines):
                                    norm_box = norm_line.get('box')
                                    if not norm_box: continue
                                    iou = calc_iou(inv_box, norm_box)
                                    if iou > best_iou:
                                        best_iou = iou
                                        match_idx = i
                                
                                # Strategy:
                                # High Overlap (>0.3): Conflict. Pick higher confidence or cleaner text.
                                # No Overlap: Add as new text (found only in inverted).
                                if best_iou > 0.3:
                                    # Conflict Resolution
                                    norm_item = fused_lines[match_idx]
                                    
                                    # Preference logic:
                                    # 1. Valid words count (avoid garbage like ".,' ")
                                    # 2. Confidence
                                    def count_valid_chars(t): return sum(c.isalnum() for c in t)
                                    norm_valid = count_valid_chars(norm_item.get('text', ''))
                                    inv_valid = count_valid_chars(inv_line.get('text', ''))
                                    
                                    norm_conf = norm_item.get('conf', 0)
                                    inv_conf = inv_line.get('conf', 0)
                                    
                                    # If inverted has significantly better valid content or confidence
                                    if inv_valid > norm_valid * 1.5 or (inv_valid >= norm_valid and inv_conf > norm_conf + 0.1):
                                        fused_lines[match_idx] = inv_line # Replace
                                else:
                                    # No overlap, assume it's white-on-black text missed by normal pass
                                    fused_lines.append(inv_line)
                                    
                            return fused_lines

                        except Exception as e:
                            # print(f"[OCR] Invert pass fusion failed: {e}")
                            pass
                    
                    return lines
                except Exception as e:
                    import traceback
                    # Only print full traceback to terminal if absolutely needed for debugging
                    # traceback.print_exc()
                    self._emit_log(f"[OCR] Internal Error in _recognize_bytes: {e}")
                    return []

            def _text_score(text: str) -> float:
                text = (text or "").strip()
                if not text:
                    return -1e9
                valid = sum(1 for ch in text if ch.isascii() and (ch.isalnum() or ch in " -'"))
                ratio = valid / max(len(text), 1)
                vowels = set("aeiouyAEIOUY")
                max_cluster = 0
                cluster = 0
                for ch in text:
                    if ch.isalpha() and ch not in vowels:
                        cluster += 1
                        if cluster > max_cluster:
                            max_cluster = cluster
                    else:
                        cluster = 0
                penalty = max(0, max_cluster - 2) * 0.1
                length_penalty = 0.01 * max(0, len(text) - 12)
                return ratio - penalty - length_penalty

            def _line_score(text: str) -> float:
                text = (text or "").strip()
                if not text:
                    return -1e9
                valid = 0
                weird = 0
                space_count = text.count(" ")
                for ch in text:
                    if ch.isascii() and (ch.isalnum() or ch in " -'.,!?;:"):
                        valid += 1
                    elif ch in "*#@$":
                        weird += 1
                ratio = valid / max(len(text), 1)
                penalty = 0.0
                if text and text[0] in "*•·":
                    penalty += 0.2
                if re.search(r"[A-Za-z]{2,}[:;][A-Za-z]", text):
                    penalty += 0.15
                if re.search(r"[A-Za-z]{2,}[,.][A-Za-z]", text):
                    penalty += 0.1
                if len(text) >= 25:
                    expected_spaces = max(1, len(text) // 8)
                    if space_count < expected_spaces:
                        penalty += 0.1
                penalty += weird * 0.05
                return ratio - penalty

            def _score_lines(lines: List[Dict[str, object]]) -> float:
                if not lines:
                    return -1e9
                texts = [str(x.get("text", "")).strip() for x in lines if str(x.get("text", "")).strip()]
                if not texts:
                    return -1e9
                joined = " ".join(texts)
                scores = [_line_score(t) for t in texts]
                avg_line = sum(scores) / max(len(scores), 1)
                valid = sum(1 for ch in joined if ch.isascii() and (ch.isalnum() or ch in " -'.,!?;:"))
                ratio = valid / max(len(joined), 1)
                words = [w for w in joined.split() if w]
                word_bonus = min(len(words) / 12.0, 1.0) * 0.2
                space_ratio = joined.count(" ") / max(len(joined), 1)
                penalty = 0.0
                if len(joined) > 40 and space_ratio < 0.05:
                    penalty += 0.2
                return avg_line + ratio * 0.5 + word_bonus - penalty

            def _scale_back_boxes(lines: List[Dict[str, object]], scale: float) -> None:
                if not lines or scale == 1.0:
                    return
                for line in lines:
                    box = line.get("box")
                    if not box:
                        continue
                    orig_box = []
                    for pt in box:
                        orig_box.append([int(pt[0] / scale), int(pt[1] / scale)])
                    line["box"] = orig_box

            def _needs_segment(text: str) -> bool:
                text = (text or "").strip()
                if len(text) < 20:
                    return False
                space_ratio = text.count(" ") / max(len(text), 1)
                if space_ratio < 0.05:
                    return True
                if re.search(r"[A-Za-z]{2,}[A-Z][a-z]", text):
                    return True
                if re.search(r"[A-Za-z]{2,}[,.!?;:][A-Za-z]", text):
                    return True
                return False

            def _segment_line(text: str) -> str:
                if not self.win_ocr_segment:
                    return text
                if not _needs_segment(text):
                    return text
                seg = self._segment_with_words_segmenter(text)
                if not seg or seg == text:
                    return text
                if _line_score(seg) >= _line_score(text) + 0.02:
                    return seg
                return text

            def _is_suspicious_line(text: str) -> bool:
                text = (text or "").strip()
                if not text:
                    return False
                if text[0] in "*•·" and len(text) > 6:
                    return True
                if re.search(r"[A-Za-z]{2,}[:;][A-Za-z]", text):
                    return True
                if re.search(r"[A-Za-z]{2,}[,.][A-Za-z]", text):
                    return True
                return False

            def _strip_leading_symbol(text: str) -> str:
                text = (text or "").strip()
                if len(text) >= 2 and text[0] in "*•·" and text[1].isalpha() and text[1].isupper():
                    return text[1:].lstrip()
                return text

            def _refine_short_lines(img_bytes: bytes, lines: List[Dict[str, object]]) -> List[Dict[str, object]]:
                if not lines:
                    return lines
                try:
                    base_img = Image.open(io.BytesIO(img_bytes))
                except Exception:
                    return lines

                refined: List[Dict[str, object]] = []
                for line in lines:
                    text = str(line.get("text", "")).strip()
                    tokens = text.split()
                    if len(tokens) != 1 or len(text) > 12:
                        refined.append(line)
                        continue
                    box = line.get("box")
                    if not box:
                        refined.append(line)
                        continue
                    try:
                        x1 = min(int(p[0]) for p in box)
                        y1 = min(int(p[1]) for p in box)
                        x2 = max(int(p[0]) for p in box)
                        y2 = max(int(p[1]) for p in box)
                    except Exception:
                        refined.append(line)
                        continue

                    pad = max(2, int((y2 - y1) * 0.2))
                    x1 = max(0, x1 - pad)
                    y1 = max(0, y1 - pad)
                    x2 = min(base_img.width, x2 + pad)
                    y2 = min(base_img.height, y2 + pad)
                    if x2 <= x1 or y2 <= y1:
                        refined.append(line)
                        continue

                    crop = base_img.crop((x1, y1, x2, y2))
                    if crop.mode != "L":
                        crop = crop.convert("L")
                    crop = ImageOps.autocontrast(crop, cutoff=10)
                    cw, ch = crop.size
                    if cw > 0 and ch > 0:
                        crop = crop.resize((int(cw * 2.0), int(ch * 2.0)), Image.Resampling.BICUBIC)

                    buf = io.BytesIO()
                    crop.save(buf, format="PNG")
                    alt_lines = _recognize_bytes(buf.getvalue(), try_invert=False)
                    alt_text = None
                    alt_score = -1e9
                    for alt in alt_lines:
                        cand = str(alt.get("text", "")).strip()
                        if not cand:
                            continue
                        score = _text_score(cand)
                        if score > alt_score + 0.01 or (abs(score - alt_score) <= 0.01 and len(cand) > len(alt_text or "")):
                            alt_score = score
                            alt_text = cand

                    if alt_text:
                        orig_score = _text_score(text)
                        if alt_score > orig_score + 0.05:
                            line = {**line, "text": alt_text}
                    refined.append(line)
                return refined

            def _refine_suspicious_lines(img_bytes: bytes, lines: List[Dict[str, object]]) -> List[Dict[str, object]]:
                if not lines:
                    return lines
                try:
                    base_img = Image.open(io.BytesIO(img_bytes))
                except Exception:
                    return lines

                refined: List[Dict[str, object]] = []
                for line in lines:
                    text = str(line.get("text", "")).strip()
                    if not _is_suspicious_line(text):
                        refined.append(line)
                        continue

                    cleaned = _strip_leading_symbol(text)
                    if cleaned != text and _line_score(cleaned) > _line_score(text) + 0.05:
                        line = {**line, "text": cleaned}
                        text = cleaned

                    box = line.get("box")
                    if not box:
                        refined.append(line)
                        continue
                    try:
                        x1 = min(int(p[0]) for p in box)
                        y1 = min(int(p[1]) for p in box)
                        x2 = max(int(p[0]) for p in box)
                        y2 = max(int(p[1]) for p in box)
                    except Exception:
                        refined.append(line)
                        continue

                    pad = max(4, int((y2 - y1) * 0.25))
                    x1 = max(0, x1 - pad)
                    y1 = max(0, y1 - pad)
                    x2 = min(base_img.width, x2 + pad)
                    y2 = min(base_img.height, y2 + pad)
                    if x2 <= x1 or y2 <= y1:
                        refined.append(line)
                        continue

                    crop = base_img.crop((x1, y1, x2, y2))
                    if crop.mode != "L":
                        crop = crop.convert("L")
                    crop = ImageOps.autocontrast(crop, cutoff=8)
                    try:
                        crop = crop.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
                    except Exception:
                        # Sharpening is an optional enhancement; if it fails, continue with the unsharpened crop
                        pass
                    cw, ch = crop.size
                    if cw > 0 and ch > 0 and ch < 80:
                        crop = crop.resize((int(cw * 2.0), int(ch * 2.0)), Image.Resampling.BICUBIC)

                    buf = io.BytesIO()
                    crop.save(buf, format="PNG")
                    alt_lines = _recognize_bytes(buf.getvalue(), try_invert=True)
                    if alt_lines:
                        alt_lines = sorted(alt_lines, key=lambda b: (b["box"][0][1], b["box"][0][0]))
                        cand = " ".join([str(b.get("text", "")).strip() for b in alt_lines if str(b.get("text", "")).strip()])
                    else:
                        cand = ""

                    if cand:
                        if _line_score(cand) > _line_score(text) + 0.05:
                            line = {**line, "text": cand}
                    refined.append(line)
                return refined

            def _refine_line_crops(img_bytes: bytes, lines: List[Dict[str, object]]) -> List[Dict[str, object]]:
                if not lines:
                    return lines
                try:
                    base_img = Image.open(io.BytesIO(img_bytes))
                except Exception:
                    return lines

                refined: List[Dict[str, object]] = []
                for line in lines:
                    text = str(line.get("text", "")).strip()
                    box = line.get("box")
                    if not text or not box:
                        refined.append(line)
                        continue
                    try:
                        x1 = min(int(p[0]) for p in box)
                        y1 = min(int(p[1]) for p in box)
                        x2 = max(int(p[0]) for p in box)
                        y2 = max(int(p[1]) for p in box)
                    except Exception:
                        refined.append(line)
                        continue

                    pad = max(4, int((y2 - y1) * 0.2))
                    x1 = max(0, x1 - pad)
                    y1 = max(0, y1 - pad)
                    x2 = min(base_img.width, x2 + pad)
                    y2 = min(base_img.height, y2 + pad)
                    if x2 <= x1 or y2 <= y1:
                        refined.append(line)
                        continue

                    crop = base_img.crop((x1, y1, x2, y2))
                    if crop.mode != "L":
                        crop = crop.convert("L")
                    crop = ImageOps.autocontrast(crop, cutoff=6)
                    try:
                        crop = crop.filter(ImageFilter.UnsharpMask(radius=1, percent=140, threshold=2))
                    except Exception:
                        # Sharpening is an optional enhancement; if it fails, continue with the unsharpened crop
                        pass
                    cw, ch = crop.size
                    if cw > 0 and ch > 0 and ch < 90:
                        crop = crop.resize((int(cw * 2.0), int(ch * 2.0)), Image.Resampling.BICUBIC)

                    buf = io.BytesIO()
                    crop.save(buf, format="PNG")
                    alt_lines = _recognize_bytes(buf.getvalue(), try_invert=True)
                    if alt_lines:
                        alt_lines = sorted(alt_lines, key=lambda b: (b["box"][0][1], b["box"][0][0]))
                        cand = " ".join([str(b.get("text", "")).strip() for b in alt_lines if str(b.get("text", "")).strip()])
                    else:
                        cand = ""

                    if cand and _line_score(cand) > _line_score(text) + 0.03:
                        line = {**line, "text": cand}
                    refined.append(line)
                return refined

            try:
                # 1. 尝试原始图片
                lines1 = _recognize_bytes(image_bytes)
                score1 = _check_quality(lines1)
                
                final_lines = lines1
                
                # 2. 如果质量低或字号过小，尝试自适应放大 (Text-Grab 策略)
                if self.win_ocr_adaptive and HAS_PIL and Image is not None:
                    # 计算平均字高
                    avg_height = 0
                    word_count = 0
                    for line in lines1:
                         # 这里 line['box'] 是 [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                         # 高度 = y2 - y1
                         box = line.get('box')
                         if box:
                             h_val = box[2][1] - box[0][1]
                             avg_height += h_val
                             word_count += 1
                    
                    if word_count > 0:
                        avg_height /= word_count
                    else:
                         avg_height = 20 # 默认假设较小

                    # 目标字高 55px (Target ~2.0x for typical 28px text to ensure clear character features)
                    ideal_height = 55.0
                    scale = 1.0
                    if avg_height < ideal_height:
                        scale = ideal_height / avg_height
                        # Snap to nearest 0.5 increment (e.g. 1.91 -> 2.0, 1.4 -> 1.5) to avoid fractional scaling artifacts
                        scale = round(scale * 2) / 2.0
                        
                        # 限制最大放大倍数
                        scale = min(scale, 3.5)
                        scale = max(scale, 1.0)
                     
                    # print(f"[OCR Debug] Quality Check: AvgHeight={avg_height:.1f}px, ScaleNeeded={scale:.2f}, Score={score1:.2f}")

                    # 如果需要放大 (且并非微小差异)，或者之前的质量评分真的很差
                    # 如果需要放大 (且并非微小差异)，或者之前的质量评分真的很差
                    if scale > 1.2 or score1 < 0.90:
                        try:
                            pil_img = None
                            
                            # Handle Raw Tuple or Bytes
                            if isinstance(image_bytes, tuple):
                                r_bytes, r_w, r_h = image_bytes
                                pil_img = Image.frombytes("RGBA", (r_w, r_h), r_bytes, "raw", "BGRA")
                            else:
                                pil_img = Image.open(io.BytesIO(image_bytes))
                            
                            w, h = pil_img.size
                            new_w, new_h = int(w * scale), int(h * scale)
                            
                            if new_w < 4000 and new_h < 4000:
                                # 使用 BICUBIC 平滑缩放 (Bicubic generally better for text shape than Bilinear if handled correctly)
                                pil_img = pil_img.resize((new_w, new_h), Image.Resampling.BICUBIC)
                                
                                # Convert to grayscale
                                if pil_img.mode != 'L':
                                    pil_img = pil_img.convert('L')
                                
                                # Gamma Correction to thin white text and reduce blooming/halos
                                # Target: Darken midtones to separate characters (fix "NewSolar" -> "New Solar")
                                try:
                                    if HAS_NUMPY and np is not None:
                                        arr = np.array(pil_img)
                                        # Gamma 1.5 (Darkens midtones: 0.5^1.5 = 0.35)
                                        # This thins white text on dark background by pushing gray edges to black
                                        arr_gamma = ((arr / 255.0) ** 1.5) * 255.0
                                        pil_img = Image.fromarray(arr_gamma.astype(np.uint8))
                                except Exception as e:
                                    print(f"[OCR] Gamma correction failed: {e}")
                                
                                buf = io.BytesIO()
                                pil_img.save(buf, format='PNG')
                                new_bytes = buf.getvalue()
                                
                                lines2 = _recognize_bytes(new_bytes)
                                score2 = _check_quality(lines2)
                                
                                # Use helper to get lengths
                                def _get_len(ls): return sum(len(x.get('text', '').strip()) for x in ls)
                                len1 = _get_len(lines1)
                                len2 = _get_len(lines2)

                                # print(f"[OCR Debug] Scaled Result: Score={score2:.2f}, Len={len2} (Original Len={len1})")
                                
                                # Accept if score improves OR if significantly more text is found (1.15x)
                                # Also accept if we scaled significantly and the result is still 'good' (score > 0.85),
                                # because small text often gives high-confidence garbage (e.g. 'I' becomes 'l').
                                if score2 >= score1 * 0.9 or len2 > len1 * 1.1 or (len1 < 10 and len2 > 10) or (scale > 1.3 and score2 > 0.85):
                                    print(f"[OCR] 自适应放大 {scale:.2f}x (AvgH={avg_height:.1f}px) 提升质量: {score1:.2f} -> {score2:.2f} (Len: {len1}->{len2})")
                                    
                                    # CRITICAL FIX: Map coordinates back to original scale
                                    # box is [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                                    for line in lines2:
                                        if 'box' in line:
                                            orig_box = []
                                            for pt in line['box']:
                                                orig_box.append([int(pt[0] / scale), int(pt[1] / scale)])
                                            line['box'] = orig_box
                                        # Also scale individual word boxes if they exist
                                        # (Note: _parse_ocr_result implementation currently doesn't attach words to line dict, 
                                        # but if it did, we'd need to scale them too. The current structure is flat lines.)
                                        
                                    final_lines = lines2
                        except Exception as e:
                             print(f"[OCR] 自适应预处理失败: {e}")

                # 2.5 多尺度识别：在不同缩放下识别，选取评分更好的结果
                if self.win_ocr_multiscale and HAS_PIL and Image is not None:
                    try:
                        # Build base image
                        base_img = None
                        if isinstance(image_bytes, tuple):
                            r_bytes, r_w, r_h = image_bytes
                            base_img = Image.frombytes("RGBA", (int(r_w), int(r_h)), r_bytes, "raw", "BGRA")
                        else:
                            base_img = Image.open(io.BytesIO(image_bytes))

                        if base_img is not None:
                            base_w, base_h = base_img.size
                            candidates: list[tuple[float, List[Dict[str, object]]]] = []
                            base_score = _score_lines(final_lines)
                            candidates.append((base_score, final_lines))

                            for scale in (1.25, 1.5, 2.0):
                                new_w, new_h = int(base_w * scale), int(base_h * scale)
                                if new_w < 200 or new_h < 80:
                                    continue
                                if new_w > 4200 or new_h > 4200:
                                    continue
                                try:
                                    resized = base_img.resize((new_w, new_h), Image.Resampling.BICUBIC)
                                    buf = io.BytesIO()
                                    resized.save(buf, format="PNG")
                                    new_bytes = buf.getvalue()
                                    lines_s = _recognize_bytes(new_bytes)
                                    if not lines_s:
                                        continue
                                    _scale_back_boxes(lines_s, scale)
                                    score_s = _score_lines(lines_s)
                                    candidates.append((score_s, lines_s))
                                except Exception:
                                    continue

                            if candidates:
                                best_score, best_lines = max(candidates, key=lambda x: x[0])
                                if best_score > base_score + 0.02:
                                    final_lines = best_lines
                    except Exception as e:
                        print(f"[OCR] 多尺度识别失败: {e}")

                if self.win_ocr_refine and HAS_PIL and Image is not None and isinstance(image_bytes, (bytes, bytearray)):
                    try:
                        final_lines = _refine_short_lines(image_bytes, final_lines)
                    except Exception as e:
                        print(f"[OCR] 短行精修失败: {e}")

                    try:
                        final_lines = _refine_suspicious_lines(image_bytes, final_lines)
                    except Exception as e:
                        print(f"[OCR] 行精修失败: {e}")

                if self.win_ocr_line_refine and HAS_PIL and Image is not None and isinstance(image_bytes, (bytes, bytearray)):
                    try:
                        final_lines = _refine_line_crops(image_bytes, final_lines)
                    except Exception as e:
                        print(f"[OCR] 行裁剪精修失败: {e}")

                if self.win_ocr_segment:
                    try:
                        for line in final_lines:
                            if "text" in line:
                                line["text"] = _segment_line(str(line.get("text", "")))
                    except Exception as e:
                        print(f"[OCR] 分词纠错失败: {e}")
                
                result_container["lines"] = final_lines
                    
            except Exception as e:
                result_container["error"] = f"{e.__class__.__name__}: {str(e)[:100]}"
        
        # 在新线程中执行OCR
        thread = threading.Thread(target=_ocr_worker, daemon=True)
        thread.start()
        thread.join(timeout=10.0)
        
        if thread.is_alive():
            print("[OCR] Windows OCR 超时")
            return []
        
        if result_container["error"]:
            print(f"[OCR] Windows OCR 识别失败：{result_container['error']}")
            return []
        
        lines = result_container["lines"]
        if lines:
            print(f"[OCR] Windows OCR (内存流) 成功识别 {len(lines)} 行文本")
        return lines

    def recognize_from_image(self, image: Union[Any, Any]) -> List[Dict[str, object]]:
        """从内存图像直接识别（OpenCV/PIL），避免硬盘读写。
        
        Args:
            image: OpenCV 图像 (numpy.ndarray) 或 PIL Image
            
        Returns:
            识别结果列表
        """
        if not HAS_PIL or Image is None:
            raise RuntimeError("需要安装 Pillow: pip install Pillow")
        
        # 转换为 PIL Image
        if np is not None and isinstance(image, np.ndarray):
            # OpenCV 图像 (BGR) → PIL Image (RGB)
            if len(image.shape) == 3 and image.shape[2] == 3:
                image = Image.fromarray(image[:, :, ::-1])  # BGR to RGB
            else:
                image = Image.fromarray(image)
        elif not isinstance(image, Image.Image):
             # 尝试直接处理，或者报错
             pass
        
        # 转换为字节流 (Optimization: Check if we can use raw path)
        if isinstance(image, Image.Image):
             # 暂时禁用 raw path，因为容易遇到参数错误，PNG 编码足够快且稳定
             pass

        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        image_bytes = buffer.getvalue()
        
        # 使用内存流识别
        return self._windows_ocr_recognize_from_bytes(image_bytes)

    def recognize(self, image_path: str | Path) -> List[str]:
        lines = self.recognize_with_confidence(image_path)
        return [text for text, _ in lines]

    def recognize_with_confidence(
        self,
        image_path: str | Path,
        backend: str | None = None,
    ) -> List[Tuple[str, float]]:
        box_lines = self.recognize_with_boxes(image_path, backend=backend)
        if not box_lines:
            return []
        return group_ocr_lines(box_lines, lang=self.lang)

    def recognize_with_boxes(
        self,
        image_input: Union[str, Path, Any],
        prefer_tesseract: bool = False,
        backend: str | None = None,
    ) -> List[Dict[str, object]]:
        """使用多后端策略识别图片中的文本框和内容。
        
        Args:
            image_input: 文件路径 (str/Path) 或 PIL Image 对象
            prefer_tesseract: 是否强制使用 Tesseract
            backend: 指定后端（auto/windows/paddle/tesseract/glm/glm_ollama）
        """
        backend_key = str(backend or "auto").strip().lower().replace("-", "_")
        if backend_key == "glm_ocr":
            backend_key = "glm"
        if backend_key not in {"auto", "windows", "paddle", "tesseract", "glm", "glm_ollama"}:
            backend_key = "auto"
        raw_tuple = None
        if isinstance(image_input, tuple) and len(image_input) == 3:
            raw_tuple = image_input
            # Keep a lazy fallback for non-Windows backends

        # 策略0: GLM-OCR (Ollama) - 显式指定
        if backend_key == "glm_ollama":
            print("[OCR] 尝试后端: GLM-OCR (Ollama)")
            glm_lines = self._glm_ollama_recognize_boxes(image_input)
            if glm_lines:
                self.last_backend = "glm_ollama"
                return glm_lines
            ollama_reason = self._shorten_error(self._glm_ollama_last_error)
            if ollama_reason:
                print(f"[OCR] GLM-OCR (Ollama) 不可用，回退到 Windows/Paddle/Tesseract（原因：{ollama_reason}）")
            else:
                print("[OCR] GLM-OCR (Ollama) 不可用，回退到 Windows/Paddle/Tesseract")
            backend_key = "auto"

        # 策略0b: GLM-OCR "glm" 重定向至 Ollama
        if backend_key == "glm":
            backend_key = "glm_ollama"
            print("[OCR] 尝试后端: GLM-OCR (Ollama)")
            glm_lines = self._glm_ollama_recognize_boxes(image_input)
            if glm_lines:
                self.last_backend = "glm_ollama"
                return glm_lines
            ollama_reason = self._shorten_error(self._glm_ollama_last_error)
            if ollama_reason:
                print(f"[OCR] GLM-OCR (Ollama) 不可用，回退到 Windows/Paddle/Tesseract（原因：{ollama_reason}）")
            else:
                print("[OCR] GLM-OCR (Ollama) 不可用，回退到 Windows/Paddle/Tesseract")
            backend_key = "auto"

        # 策略1: 如果明确要求 Tesseract，直接使用
        if prefer_tesseract or backend_key == "tesseract":
            print("[OCR] 使用后端: Tesseract (明确指定)")
            self.last_backend = "tesseract"
            if raw_tuple and HAS_PIL and Image is not None:
                r_bytes, r_w, r_h = raw_tuple
                image_input = Image.frombytes("RGBA", (int(r_w), int(r_h)), r_bytes, "raw", "BGRA")
            return self._pytesseract_recognize_boxes(image_input)
        
        # 策略2: 尝试 Windows 原生 OCR（默认优先）
        if backend_key in {"auto", "windows"}:
            print("[OCR] 尝试后端: Windows OCR (优先)")
            windows_lines = []
            if self.win_ocr_preprocess:
                pre_bytes = self._preprocess_windows_input(raw_tuple if raw_tuple is not None else image_input)
                if pre_bytes:
                    windows_lines = self._windows_ocr_recognize_from_bytes(pre_bytes)
            if not windows_lines:
                if isinstance(image_input, (str, Path)):
                     # File Path
                     windows_lines = self._windows_ocr_recognize_boxes(image_input)
                elif raw_tuple is not None:
                     windows_lines = self._windows_ocr_recognize_from_bytes(raw_tuple)
                else:
                     # PIL Image or Object
                     windows_lines = self.recognize_from_image(image_input)
                 
            if windows_lines:
                self.last_backend = "windows"
                return windows_lines

        # Prepare fallback input for non-Windows backends
        if raw_tuple is not None and HAS_PIL and Image is not None:
            r_bytes, r_w, r_h = raw_tuple
            image_input = Image.frombytes("RGBA", (int(r_w), int(r_h)), r_bytes, "raw", "BGRA")
        
        # 策略4: 尝试 PaddleOCR
        allow_paddle = bool(getattr(self, "allow_paddle", True)) or backend_key == "paddle"
        if allow_paddle and backend_key == "paddle" and self._ocr is None:
            self.initialize(force_paddle=True, allow_paddle=True)
        elif allow_paddle and not self.ready and backend_key in {"paddle", "auto"}:
            self.initialize(allow_paddle=True)

        if allow_paddle and self._ocr is not None:
            print("[OCR] 尝试后端: PaddleOCR")
            try:
                # Prepare input for Paddle (Path string or Numpy Array)
                paddle_input = image_input
                if not isinstance(paddle_input, (str, Path)) and HAS_NUMPY and np is not None:
                     if isinstance(paddle_input, Image.Image):
                         paddle_input = np.array(paddle_input)
                
                # If path, ensure string
                if isinstance(paddle_input, Path):
                     paddle_input = str(paddle_input)

                if self._supports_cls:
                    result = self._ocr.ocr(paddle_input, cls=self.cls)
                else:
                    result = self._ocr.ocr(paddle_input)
            except Exception as e:
                print(f"[OCR] PaddleOCR 运行失败：{e.__class__.__name__}, 回退到 Tesseract")
                result = None
        else:
            print("[OCR] 跳过 PaddleOCR (未安装或未初始化)")
            result = None
        
        # 策略5: 最后的兜底 Tesseract
        if not result:
            print("[OCR] 使用后端: Tesseract (最后兜底)")
            self.last_backend = "tesseract"
            return self._pytesseract_recognize_boxes(image_input)
        
        lines = self._paddle_extract_lines(result)
        
        # 策略5: 质量检查 - 如果 PaddleOCR 结果质量差，尝试 Tesseract 兜底
        if lines:
            avg_conf = sum(float(x.get("conf", 0.0)) for x in lines) / max(len(lines), 1)
            print(f"[OCR] PaddleOCR 完成，识别 {len(lines)} 行，平均置信度 {avg_conf:.3f}")
            
            if avg_conf < 0.6 and len(lines) > 6:
                print("[OCR] PaddleOCR 质量较低，尝试 Tesseract 兜底")
                fallback = self._pytesseract_recognize_boxes(image_input)
                if fallback:
                    fallback_conf = sum(float(x.get("conf", 0.0)) for x in fallback) / max(len(fallback), 1)
                    if fallback_conf > avg_conf:
                        print(f"[OCR] Tesseract 结果更优 ({fallback_conf:.3f} > {avg_conf:.3f})，使用 Tesseract")
                        self.last_backend = "tesseract"
                        return fallback
        
        self.last_backend = "paddle"
        return lines

    def _pytesseract_recognize(self, image_path: str | Path) -> List[Tuple[str, float]]:
        if self._pytesseract is None:
            try:
                import pytesseract
            except Exception as exc:  # pragma: no cover
                print("PaddleOCR 失败且 pytesseract 不可用")
                return []
            self._pytesseract = pytesseract

            # 优先使用环境变量或常见安装路径，避免未添加到 PATH 导致的找不到可执行文件
            candidate_env = os.getenv("TESSERACT_CMD") or os.getenv("TESSERACT_PATH")
            candidates = [
                candidate_env,
                shutil.which("tesseract"),
                Path(r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"),
                Path(r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe"),
                Path("/usr/bin/tesseract"),
                Path("/usr/local/bin/tesseract"),
            ]
            for candidate in candidates:
                if not candidate:
                    continue
                candidate_path = Path(candidate)
                if candidate_path.exists():
                    self._pytesseract.pytesseract.tesseract_cmd = str(candidate_path)
                    break

        try:
            from PIL import Image
            from pytesseract import Output
        except Exception:
            return []

        try:
            data = self._pytesseract.image_to_data(
                Image.open(image_path), output_type=Output.DICT
            )
        except Exception:
            print("tesseract 未安装或不可用，OCR 跳过")
            return []
        texts: List[Tuple[str, float]] = []
        for text, conf in zip(data.get("text", []), data.get("conf", [])):
            if not text or text.strip() == "":
                continue
            try:
                conf_val = float(conf) / 100.0
            except Exception:
                conf_val = 0.0
            texts.append((text.strip(), conf_val))
        return texts

    def _pytesseract_recognize_boxes(self, image_input: Union[str, Path, Any]) -> List[Dict[str, object]]:
        if self._pytesseract is None:
            try:
                import pytesseract
            except Exception:
                return []
            self._pytesseract = pytesseract

            candidate_env = os.getenv("TESSERACT_CMD") or os.getenv("TESSERACT_PATH")
            candidates = [
                candidate_env,
                shutil.which("tesseract"),
                Path(r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"),
                Path(r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe"),
                Path("/usr/bin/tesseract"),
                Path("/usr/local/bin/tesseract"),
            ]
            for candidate in candidates:
                if not candidate:
                    continue
                candidate_path = Path(candidate)
                if candidate_path.exists():
                    self._pytesseract.pytesseract.tesseract_cmd = str(candidate_path)
                    break

        try:
            from PIL import Image
            from pytesseract import Output
        except Exception:
            return []

        if isinstance(image_input, tuple) and len(image_input) == 3:
            try:
                r_bytes, r_w, r_h = image_input
                image_input = Image.frombytes("RGBA", (int(r_w), int(r_h)), r_bytes, "raw", "BGRA")
            except Exception:
                return []

        lang = "eng" if self.lang.startswith("en") else self.lang
        configs = [
            f"--oem 1 --psm 6 -l {lang} -c preserve_interword_spaces=1",
            f"--oem 1 --psm 4 -l {lang} -c preserve_interword_spaces=1",
            f"--oem 1 --psm 3 -l {lang} -c preserve_interword_spaces=1",
        ]

        best_lines: List[Dict[str, object]] = []
        best_score = -1.0
        for cfg in configs:
            try:
                img_source = image_input
                if isinstance(img_source, (str, Path)):
                    img_source = Image.open(str(img_source))
                
                data = self._pytesseract.image_to_data(
                    img_source, output_type=Output.DICT, config=cfg
                )
            except Exception:
                continue
            lines: List[Dict[str, object]] = []
            for text, conf, left, top, width, height in zip(
                data.get("text", []),
                data.get("conf", []),
                data.get("left", []),
                data.get("top", []),
                data.get("width", []),
                data.get("height", []),
            ):
                if not text or text.strip() == "":
                    continue
                try:
                    conf_val = float(conf) / 100.0
                except Exception:
                    conf_val = 0.0
                box = [
                    [int(left), int(top)],
                    [int(left) + int(width), int(top)],
                    [int(left) + int(width), int(top) + int(height)],
                    [int(left), int(top) + int(height)],
                ]
                lines.append({"text": text.strip(), "conf": conf_val, "box": box})

            if not lines:
                continue
            avg_conf = sum(float(x.get("conf", 0.0)) for x in lines) / max(len(lines), 1)
            total_len = sum(len(str(x.get("text", ""))) for x in lines)
            score = avg_conf + min(total_len / 200.0, 1.0)
            if score > best_score:
                best_score = score
                best_lines = lines
        return best_lines


def group_ocr_lines(box_lines: List[Dict[str, object]], lang: str = "en") -> List[Tuple[str, float]]:
    """
    对 OCR 原始结果进行几何分行。
    仅依据垂直位置和高度进行行聚合，严禁语义合并。
    """
    if not box_lines:
        return []

    # 1. Sort by Y (top-down), then X (left-right)
    # 必须先按 Y 排序才能线性聚类
    lines_sorted = sorted(box_lines, key=lambda b: (b["box"][0][1], b["box"][0][0]))
    
    merged_lines: List[List[Dict[str, Any]]] = []
    
    for item in lines_sorted:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
            
        if not merged_lines:
            merged_lines.append([item])
            continue
            
        current_line = merged_lines[-1]
        last_item = current_line[-1]
        
        # Geometry
        last_y1 = last_item["box"][0][1]
        last_h = last_item["box"][2][1] - last_y1
        curr_y1 = item["box"][0][1]
        curr_h = item["box"][2][1] - curr_y1
        
        # 垂直中心距离
        last_cy = last_y1 + last_h / 2.0
        curr_cy = curr_y1 + curr_h / 2.0
        v_dist = abs(last_cy - curr_cy)
        
        # 判定同行：垂直错位小于最小高度的一半
        is_same_line = v_dist < (min(last_h, curr_h) * 0.5)
        
        if is_same_line:
            current_line.append(item)
            # 保持行内从左到右有序
            current_line.sort(key=lambda b: b["box"][0][0])
        else:
            merged_lines.append([item])

    # Phase 2: Paragraph Merging
    # 将垂直间距较小的视觉行合并为段落，避免句子被切断
    final_output: List[Tuple[str, float]] = []
    
    if merged_lines:
        para_groups = []
        current_para = [merged_lines[0]]
        
        for i in range(1, len(merged_lines)):
            last_line = current_para[-1]
            curr_line = merged_lines[i]
            
            # Calc geometry
            l_y1 = min(t["box"][0][1] for t in last_line)
            l_y2 = max(t["box"][2][1] for t in last_line)
            l_h = l_y2 - l_y1
            
            c_y1 = min(t["box"][0][1] for t in curr_line)
            c_y2 = max(t["box"][2][1] for t in curr_line)
            c_h = c_y2 - c_y1
            
            gap = c_y1 - l_y2
            
            # Threshold: Gap < 0.5 * LineHeight (Reduced from 0.8)
            allowed_gap = min(l_h, c_h) * 0.5
            
            # Extra Check: Horizontal Indentation
            # If start position differs significantly (> 50px), enforce stricter gap or force split
            l_x1 = min(t["box"][0][0] for t in last_line)
            c_x1 = min(t["box"][0][0] for t in curr_line)
            
            if abs(c_x1 - l_x1) > 50:
                 allowed_gap = min(l_h, c_h) * 0.2  # Very strict if not aligned
            
            if gap < allowed_gap:
                current_para.append(curr_line)
            else:
                para_groups.append(current_para)
                current_para = [curr_line]
        para_groups.append(current_para)
        
        # Flatten paragraphs
        for para in para_groups:
            # Flatten all items in paragraph
            all_items = [item for line in para for item in line]
            
            # Sort by Y then X again just to be safe? 
            # No, within paragraph logic, lines are ordered Y, words ordered X.
            # Concatenation is correct reading order.
            
            valid_items = [t for t in all_items if str(t.get("text", "")).strip()]
            if not valid_items:
                continue
                
            tokens = [str(t.get("text", "")).strip() for t in valid_items]
            full_text = " ".join(tokens)
            
            confs = [float(t.get("conf", 1.0)) for t in valid_items]
            avg_conf = sum(confs) / max(len(confs), 1)
            
            # Basic cleanup
            for punct in [",", ".", "!", "?", ";", ":"]:
                full_text = full_text.replace(f" {punct}", punct)
            
            final_output.append((full_text, avg_conf))

    return final_output
