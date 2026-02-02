from __future__ import annotations

import os
import shutil
import threading
import io
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union, cast

import re
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


class OCREngine:
    """封装 PaddleOCR。"""

    def __init__(
        self,
        lang: str = "en",
        use_gpu: bool = False,
        mode: str | None = None,
        det: bool = True,
        rec: bool = True,
        cls: bool = False,
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

    def set_mode(self, mode: str) -> None:
        self.mode = mode.lower()
        self.ready = False
        self._ocr = None

    def initialize(self) -> None:
        """初始化 OCR 引擎。

        策略：
        1. 总是初始化 Windows OCR（如果可用）。
        2. 只有在明确指定paddle模式或auto模式下Windows OCR不可用时才加载PaddleOCR。
        """
        # 1. 初始化 Windows OCR (轻量级)
        self._init_windows_ocr()

        # 2. 检查是否需要加载 PaddleOCR
        # 如果是 winrt 模式，或 auto 模式下 Windows OCR 可用，则无需加载 Paddle
        if self.mode == "winrt":
             print("[OCR] 模式=winrt，无需加载 PaddleOCR")
             return

        if self.mode == "auto" and self._windows_ocr is not None:
             print("[OCR] 模式=auto 且 Windows OCR 可用，无需加载 PaddleOCR")
             return

        if self.mode == "tesseract":
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
                    self._supports_cls = "cls" in extra
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
            print(f"[OCR] Windows OCR 不可用：WinRT 依赖缺失 ({e.__class__.__name__})")
            print("[OCR] 提示：可通过 'pip install winrt-Windows.Media.Ocr winrt-Windows.Globalization' 安装")
            self._windows_ready = True
            self._windows_ocr = None
            return
        except Exception as e:
            print(f"[OCR] Windows OCR 导入失败：{e.__class__.__name__}: {e}")
            self._windows_ready = True
            self._windows_ocr = None
            return
        
        # 检查可用的语言包
        try:
            available_langs = OcrEngine.available_recognizer_languages
            available_lang_codes = [lang.language_tag for lang in available_langs]
            print(f"[OCR] Windows OCR 可用语言包: {', '.join(available_lang_codes) if available_lang_codes else '无'}")
        except Exception as e:
            print(f"[OCR] 无法检查语言包：{e}")
            available_lang_codes = []
        
        # 尝试创建 OCR 引擎实例
        try:
            print(f"[OCR Config] Requesting Lang: {self.lang}")
            if self.lang.startswith("en"):
                # Try specific US English first
                lang = Language("en-US")
                if not OcrEngine.is_language_supported(lang):
                     print("[OCR Config] en-US not supported, checking others...")
                
                self._windows_ocr = OcrEngine.try_create_from_language(lang)
                if self._windows_ocr is None:
                    # Fallback to en-GB if en-US missing (common in some regions)
                    print("[OCR] Windows OCR: en-US failed, trying en-GB")
                    lang_gb = Language("en-GB")
                    self._windows_ocr = OcrEngine.try_create_from_language(lang_gb)

                if self._windows_ocr is None:
                    print("[OCR] Windows OCR：en-US 语言包未安装")
                    if "en-US" not in available_lang_codes and "en" not in available_lang_codes:
                        print("[OCR] 提示：请安装英语语言包")
                        print("[OCR]   设置 -> 时间和语言 -> 语言 -> 添加语言 -> English (United States)")
                    print("[OCR] 尝试使用系统默认语言包...")
                    self._windows_ocr = OcrEngine.try_create_from_user_profile_languages()
            elif self.lang.startswith("zh"):
                lang = Language("zh-CN")
                self._windows_ocr = OcrEngine.try_create_from_language(lang)
                if self._windows_ocr is None:
                    print("[OCR] Windows OCR：zh-CN 语言包未安装")
                    if "zh-CN" not in available_lang_codes and "zh" not in available_lang_codes:
                        print("[OCR] 提示：请安装中文语言包")
                        print("[OCR]   设置 -> 时间和语言 -> 语言 -> 添加语言 -> 中文(简体，中国)")
                    print("[OCR] 尝试使用系统默认语言包...")
                    self._windows_ocr = OcrEngine.try_create_from_user_profile_languages()
            else:
                self._windows_ocr = OcrEngine.try_create_from_user_profile_languages()
            
            if self._windows_ocr is None:
                print("[OCR] Windows OCR 不可用：系统未安装任何 OCR 语言包")
                print("[OCR] 请在 Windows 设置中安装语言包：")
                print("[OCR]   设置 -> 时间和语言 -> 语言 -> 添加语言")
            else:
                lang_tag = self._windows_ocr.recognizer_language.language_tag if self._windows_ocr.recognizer_language else "unknown"
                print(f"[OCR] Windows OCR 初始化成功 (使用语言: {lang_tag})")
        except Exception as e:
            print(f"[OCR] Windows OCR 初始化失败：{e.__class__.__name__}: {e}")
            self._windows_ocr = None
        
        self._windows_ready = True

    def _windows_ocr_recognize_boxes(self, image_path: str | Path) -> List[Dict[str, object]]:
        """使用 Windows 原生 OCR 识别图片中的文本。
        
        注意：WinRT 异步操作在GUI线程（STA）中可能失败，因此在单独线程中执行。
        """
        # 读取文件内容直接传给字节流处理方法
        try:
            data = Path(image_path).read_bytes()
            return self._windows_ocr_recognize_from_bytes(data)
        except Exception as e:
            print(f"[OCR] 读取文件失败：{e}")
            return []


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
            try:
                from winrt.windows.storage.streams import InMemoryRandomAccessStream, DataWriter
                from winrt.windows.graphics.imaging import BitmapDecoder, SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode
            except ImportError:
                result_container["error"] = "WinRT模块导入失败"
                return
            except Exception as e:
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

            def _parse_ocr_result(result):
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
                        # 增大阈值以避免单词断裂
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

            def _recognize_bytes(bytes_data, try_invert=True):
                try:
                    stream = InMemoryRandomAccessStream()
                    writer = DataWriter(stream)
                    writer.write_bytes(bytes_data)
                    writer.store_async().get()
                    writer.flush_async().get()
                    writer.detach_stream()
                    stream.seek(0)
                    
                    decoder = BitmapDecoder.create_async(stream).get()
                    bitmap = decoder.get_software_bitmap_async().get()
                    
                    # 性能优化：转换为 Bgra8 格式 (适合截图)
                    bitmap = _ensure_bgra8(bitmap)

                    if not self._windows_ocr:
                        return []
                        
                    # Pass 1: Normal Recognition
                    result = self._windows_ocr.recognize_async(bitmap).get()
                    lines = _parse_ocr_result(result)
                    
                    # Pass 2: Inverted Logic (Dual-Pass Strategy)
                    # DOCUMENTATION: "OCR 引擎对黑底白字识别能力弱，必须使用双通逻辑"
                    # Always try invert if enabled, then pick the best result.
                    if try_invert:
                        try:
                            if HAS_PIL and Image is not None:
                                import io
                                pil_img = Image.open(io.BytesIO(bytes_data))
                                if pil_img.mode == 'RGBA':
                                    pil_img = pil_img.convert('RGB')
                                
                                from PIL import ImageOps
                                inv_img = ImageOps.invert(pil_img)
                                
                                buf = io.BytesIO()
                                inv_img.save(buf, format='PNG')
                                inv_bytes = buf.getvalue()
                                
                                # Recursive call without convert/invert logic (pass try_invert=False)
                                inv_lines = _recognize_bytes(inv_bytes, try_invert=False)
                                
                                # Fusion Strategy: Pick result with more *alphanumeric* content
                                def _get_content_len(ls):
                                    return sum(len(x['text'].strip()) for x in ls)
                                
                                len_normal = _get_content_len(lines)
                                len_inv = _get_content_len(inv_lines)
                                
                                text_norm = " ".join([x['text'] for x in lines])[:30]
                                text_inv = " ".join([x['text'] for x in inv_lines])[:30]
                                # print(f"[OCR Debug] Dual-Pass: NormLen={len_normal} InvLen={len_inv}")
                                # print(f"  Norm: {text_norm}")
                                # print(f"  Inv : {text_inv}")
                                
                                # Prefer inverted if it has significantly more text
                                if len_inv > len_normal * 1.2 or (len_normal < 10 and len_inv > 10):
                                    # print(f"[OCR] Using Inverted Pass result ({len_inv} > {len_normal})")
                                    return inv_lines
                        except Exception as e:
                            # print(f"[OCR] Invert pass warning: {e}")
                            pass
                            
                    return lines
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    print(f"[OCR] Internal Error in _recognize_bytes: {e}")
                    return []

            try:
                # 1. 尝试原始图片
                lines1 = _recognize_bytes(image_bytes)
                score1 = _check_quality(lines1)
                # print(f"[OCR Debug] Score: {score1:.3f}")
                
                final_lines = lines1
                
                # 2. 如果质量低或字号过小，尝试自适应放大 (Text-Grab 策略)
                if HAS_PIL and Image is not None:
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

                    # 目标字高 40px (WinRT OCR Sweet Spot)
                    ideal_height = 40.0
                    scale = 1.0
                    if avg_height < ideal_height:
                        scale = ideal_height / avg_height
                        # 限制最大放大倍数
                        scale = min(scale, 3.5)
                    
                    # print(f"[OCR Debug] Quality Check: AvgHeight={avg_height:.1f}px, ScaleNeeded={scale:.2f}, Score={score1:.2f}")

                    # 如果需要放大 (且并非微小差异)，或者之前的质量评分真的很差
                    if scale > 1.2 or score1 < 0.90:
                        try:
                            import io
                            pil_img = Image.open(io.BytesIO(image_bytes))
                            
                            w, h = pil_img.size
                            new_w, new_h = int(w * scale), int(h * scale)
                            
                            if new_w < 4000 and new_h < 4000:
                                # 使用 BICUBIC 平滑缩放，保留灰度抗锯齿信息 (不使用 LANCZOS/二值化)
                                pil_img = pil_img.resize((new_w, new_h), Image.Resampling.BICUBIC)
                                
                                # 增强对比度并锐化
                                from PIL import ImageOps, ImageFilter
                                if pil_img.mode != 'L':
                                    pil_img = pil_img.convert('L')
                                
                                # 使用直方图均衡化可能更有助于低对比度文本，但有时会增加噪声
                                # 文档建议：CLAHE (OpenCV) 最好，但在纯 PIL 环境下，
                                # Autocontrast with cutoff + Sharpness is a good approximation.
                                pil_img = ImageOps.autocontrast(pil_img, cutoff=2)
                                pil_img = pil_img.filter(ImageFilter.SHARPEN)
                                # 再次稍微增强一点对比度，确保锐化后清晰
                                pil_img = ImageOps.autocontrast(pil_img, cutoff=1)
                                
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
                                # This handles cases where original had high score but missed a lot of text
                                if score2 >= score1 or len2 > len1 * 1.15 or (len1 < 10 and len2 > 10):
                                    print(f"[OCR] 自适应放大 {scale:.2f}x (AvgH={avg_height:.1f}px) 提升质量: {score1:.2f} -> {score2:.2f} (Len: {len1}->{len2})")
                                    final_lines = lines2
                        except Exception as e:
                             print(f"[OCR] 自适应预处理失败: {e}")
                
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
        
        # 转换为字节流
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        image_bytes = buffer.getvalue()
        
        # 使用内存流识别
        return self._windows_ocr_recognize_from_bytes(image_bytes)

    def recognize(self, image_path: str | Path) -> List[str]:
        lines = self.recognize_with_confidence(image_path)
        return [text for text, _ in lines]

    def recognize_with_confidence(self, image_path: str | Path) -> List[Tuple[str, float]]:
        if not self.ready:
            self.initialize()
        
        if self._ocr is None:
            # 如果 Paddle 不可用，直退 Tesseract
            return self._pytesseract_recognize(image_path)

        try:
            if self._supports_cls:
                result = self._ocr.ocr(str(image_path), cls=self.cls)
            else:
                result = self._ocr.ocr(str(image_path))
        except NotImplementedError:
            return self._pytesseract_recognize(image_path)
        texts: List[Tuple[str, float]] = []
        if not result:
            return texts
        for block in result:
            for item in block:
                text = item[1][0]
                conf = float(item[1][1])
                texts.append((text, conf))
        return texts

    def recognize_with_boxes(
        self, image_path: str | Path, prefer_tesseract: bool = False
    ) -> List[Dict[str, object]]:
        """使用多后端策略识别图片中的文本框和内容。
        
        优先级：Windows OCR > PaddleOCR > Tesseract (auto模式)
        """
        # 策略1: 如果明确要求 Tesseract，直接使用
        if prefer_tesseract:
            print("[OCR] 使用后端: Tesseract (明确指定)")
            self.last_backend = "tesseract"
            return self._pytesseract_recognize_boxes(image_path)
        
        # 策略2: 优先尝试 Windows 原生 OCR (最快且准确)
        print("[OCR] 尝试后端: Windows OCR (优先)")
        windows_lines = self._windows_ocr_recognize_boxes(image_path)
        if windows_lines:
            self.last_backend = "windows"
            return windows_lines
        
        # 策略3: 尝试 PaddleOCR
        if not self.ready:
            self.initialize()
            
        if self._ocr is not None:
            print("[OCR] 尝试后端: PaddleOCR")
            try:
                if self._supports_cls:
                    result = self._ocr.ocr(str(image_path), cls=self.cls)
                else:
                    result = self._ocr.ocr(str(image_path))
            except Exception as e:
                print(f"[OCR] PaddleOCR 运行失败：{e.__class__.__name__}, 回退到 Tesseract")
                result = None
        else:
            print("[OCR] 跳过 PaddleOCR (未安装或未初始化)")
            result = None
        
        # 策略4: 最后的兜底 Tesseract
        if not result:
            print("[OCR] 使用后端: Tesseract (最后兜底)")
            self.last_backend = "tesseract"
            return self._pytesseract_recognize_boxes(image_path)
        
        lines: List[Dict[str, object]] = []
        for block in result:
            for item in block:
                box = item[0]
                text = item[1][0]
                conf = float(item[1][1])
                lines.append({"text": text, "conf": conf, "box": box})
        
        # 策略4: 质量检查 - 如果 PaddleOCR 结果质量差，尝试 Tesseract 兜底
        if lines:
            avg_conf = sum(float(x.get("conf", 0.0)) for x in lines) / max(len(lines), 1)
            print(f"[OCR] PaddleOCR 完成，识别 {len(lines)} 行，平均置信度 {avg_conf:.3f}")
            
            if avg_conf < 0.6 and len(lines) > 6:
                print("[OCR] PaddleOCR 质量较低，尝试 Tesseract 兜底")
                fallback = self._pytesseract_recognize_boxes(image_path)
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

    def _pytesseract_recognize_boxes(self, image_path: str | Path) -> List[Dict[str, object]]:
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
                data = self._pytesseract.image_to_data(
                    Image.open(image_path), output_type=Output.DICT, config=cfg
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
    对 OCR 原始结果进行可视化分组和合并。
    ...
    """
    """将 OCR 结果按坐标分行，并按从上到下、从左到右拼接为行文本。
    
    智能分组策略：
    1. 基本分行：按y坐标中心距离判断是否同一行
    2. 对话模式：识别"标题+多行内容"模式，自动合并对话行
    3. 二次分割：按冒号、特殊符号等分隔符进一步拆分
    """
    import re
    items: List[Dict[str, object]] = []
    for item in box_lines:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        conf = float(item.get("conf", 0.0))
        box = item.get("box") or []
        if len(box) >= 4:
            xs = [cast(float, pt[0]) for pt in box]
            ys = [cast(float, pt[1]) for pt in box]
            x1, x2 = float(min(xs)), float(max(xs))
            y1, y2 = float(min(ys)), float(max(ys))
        else:
            x1 = y1 = 0.0
            x2 = y2 = 0.0
        h = max(y2 - y1, 1.0)
        cy = y1 + h / 2.0
        # 过滤过短且低置信的噪声
        if conf < 0.2 and len(text) < 4:
            continue
        items.append({"text": text, "conf": conf, "x1": x1, "x2": x2, "y1": y1, "cy": cy, "h": h})

    if not items:
        return []

    items.sort(key=lambda x: cast(float, x["cy"]))
    lines: List[List[Dict[str, object]]] = []
    current: List[Dict[str, object]] = []
    current_y = None
    current_h = None
    for item in items:
        if not current:
            current = [item]
            current_y = cast(float, item["cy"])
            current_h = cast(float, item["h"])
            continue
        # 更加宽松的分行阈值，允许一定程度的倾斜或基线不齐
        threshold = max(15.0, float(current_h) * 0.8)
        if current_y is not None and abs(cast(float, item["cy"]) - current_y) <= threshold:
            current.append(item)
            # 缓慢平均行中心
            current_y = (current_y * 2 + cast(float, item["cy"])) / 3.0
            current_h = max(float(current_h), cast(float, item["h"]))
        else:
            lines.append(current)
            current = [item]
            current_y = cast(float, item["cy"])
            current_h = cast(float, item["h"])
    if current:
        lines.append(current)

    # 构建初步输出
    initial_output: List[Tuple[str, float, bool, float, float]] = []  # (text, conf, is_title, group_y, group_h)
    for line in lines:
        line.sort(key=lambda x: cast(float, x["x1"]))
        
        # 检查是否需要拆分同一行的元素
        # 如果X坐标间距过大，说明是独立的标签/元素
        line_items = []
        for i, item in enumerate(line):
            if i == 0:
                line_items.append([item])
            else:
                prev_item = line[i-1]
                # 计算实际 X 间距
                gap = cast(float, item["x1"]) - cast(float, prev_item["x2"])
                # 如果间距 > 80px (或者行高的2倍)，认为是独立元素
                if gap > max(80.0, cast(float, item["h"]) * 2.5):
                    line_items.append([item])
                else:
                    line_items[-1].append(item)
        
        # 对每组独立元素分别处理
        for item_group in line_items:
            tokens = [str(t["text"]) for t in item_group]
            confs = [float(t["conf"]) for t in item_group]
            # 保留Y坐标和高度信息
            y_coords = [float(t["y1"]) for t in item_group]
            heights = [float(t["h"]) for t in item_group]
            group_y = sum(y_coords) / len(y_coords)
            group_h = sum(heights) / len(heights)
            
            text = " ".join(tokens)
            # 简单清理标点空格
            for punct in [",", ".", "!", "?", ";", ":"]:
                text = text.replace(f" {punct}", punct)
            avg_conf = sum(confs) / max(len(confs), 1)
            
            # 判断是否为标题行（短文本，通常是角色名或任务名）
            word_count = len(text.split())
            char_count = len(text)
            # 检查是否为内容性标点（排除缩写中的句号，如 Ms., Dr., Mr.）
            # 内容的特征：
            # 1. 包含句内标点（逗号、问号、叹号、冒号）
            # 2. 以句号结尾（任何以句号结尾的都视为句子片段，包括"Solution.", "immediately."等）
            stripped = text.rstrip()
            ends_with_period = stripped.endswith('.')
            has_sentence_punct = any(ch in text for ch in [',', '!', '?'])
            # 末尾冒号不算句子标点（可能是标题格式 "Title: Subtitle"）
            has_trailing_colon = text.strip().endswith(':')
            
            # 判断为句子/内容的条件：有标点符号（但末尾冒号除外）
            is_likely_sentence = has_sentence_punct or (ends_with_period and not has_trailing_colon)
            
            # 标题特征：短文本（≤3词 且 ≤30字符）且 无句子标点
            # 允许末尾冒号（如 "Event Title:"）
            # 标题特征：极短文本（≤3词 且 ≤30字符）且 无句子结束标点
            # 修正：如果内容全是小写或者是个残缺单词，不应视为标题
            is_fragment = word_count == 1 and not text[0].isupper()
            is_title = (word_count <= 3 and char_count <= 30 and not is_likely_sentence) and not is_fragment
            
            # --- 文本清洗 (兜底修复模型幻觉) ---
            if lang.startswith("en"):
                # 针对 en-GB 模型容易出现的 scandinavian 字符幻觉进行替换
                # 替换 å -> a, ø -> o, é -> e, ö -> o, ä -> a 等 (在纯英文语境下通常是误识别)
                # 注意：某些游戏名可能包含法语重音，需谨慎。但 å, ö, ä 极少出现在现代英文普通单词中。
                replacements = {
                    'å': 'a', 'Å': 'A', 
                    'ø': 'o', 'Ø': 'O', 
                    'æ': 'ae', 'Æ': 'AE',
                    'ö': 'o', 'Ö': 'O',
                    'ä': 'a', 'Ä': 'A',
                    'ë': 'e', 'Ë': 'E',
                    'ï': 'i', 'Ï': 'I',
                    'ü': 'u', 'Ü': 'U',
                }
                # 仅当单词看起来像英文时替换 (简单启发式)
                new_text = ""
                for word in text.split():
                    # 检查是否包含乱码字符
                    if any(c in replacements for c in word):
                        # 执行替换
                        clean_word = "".join(replacements.get(c, c) for c in word)
                        new_text += clean_word + " "
                    else:
                        new_text += word + " "
                text = new_text.strip()
            # ----------------------------------
            
            initial_output.append((text, avg_conf, is_title, group_y, group_h))
    
    # 智能合并：识别并合并段落
    final_output: List[Tuple[str, float]] = []
    
    if len(initial_output) >= 1:
        i = 0
        while i < len(initial_output):
            text, conf, is_title, y, h = initial_output[i]
            
            # 如果是标题，且后面紧跟着内容，尝试判断是否为"姓名: 对话"模式
            if is_title:
                # 检查是否应该与下一行合并（如果下一行是内容且间距极小）
                can_merge_with_next = False
                if i + 1 < len(initial_output):
                    next_text, next_conf, next_is_title, next_y, next_h = initial_output[i+1]
                    y_gap = next_y - (y + h)
                    # 如果间距极小（< 0.5倍行高），且当前是短标题，可能是残卷或由于OCR导致的错误换行
                    if y_gap < h * 0.5 and not next_is_title:
                        can_merge_with_next = True
                
                if can_merge_with_next:
                    # 将标题和下一行合并（内容合并模式）
                    is_title = False # 降级为内容，让下面的内容合并逻辑处理
                else:
                    # 保持作为独立标题/姓名
                    final_output.append((text, conf))
                    i += 1
                    continue

            # 内容合并逻辑
            content_group = [initial_output[i]]
            prev_y_bottom = y + h
            prev_h = h
            current_is_title = is_title
            i += 1
            
            while i < len(initial_output):
                n_text, n_conf, n_is_title, n_y, n_h = initial_output[i]
                y_gap = n_y - prev_y_bottom
                
                # 系统信息检测：纯数字、大量数字或超长数字段
                digit_ratio = sum(c.isdigit() for c in n_text) / max(len(n_text), 1)
                is_system_info = digit_ratio > 0.4 or re.search(r'\d{8,}', n_text)
                
                if is_system_info:
                    break

                # 合并条件：
                # 1. 下一行不是标题
                # 2. 或者 下一行是标题但间距极小且上一行没结束
                should_merge = False
                if not n_is_title:
                    # 正常内容合并
                    is_visual_gap = y_gap > prev_h * 1.6
                    # 只要没结束且间距合理就合并
                    if not is_visual_gap:
                        should_merge = True
                else:
                    # 标题合并：只有在间距极小且上一行不是以句号结尾时才合并（处理OCR断词）
                    if y_gap < prev_h * 0.4 and not content_group[-1][0].rstrip().endswith('.'):
                        should_merge = True
                
                if not should_merge:
                    break
                    
                content_group.append(initial_output[i])
                prev_y_bottom = n_y + n_h
                prev_h = n_h
                i += 1
            
            merged_content = " ".join([t[0] for t in content_group])
            avg_conf = sum(t[1] for t in content_group) / len(content_group)
            final_output.append((merged_content, avg_conf))
    else:
        final_output = [(text, conf) for text, conf, _, _, _ in initial_output]
    
    # 二次分割：处理混合条目（如 "Event Duration: Permanent"）
    # 按冒号分割，但只分割明确的“标签：值”格式
    split_output: List[Tuple[str, float]] = []
    
    # 常见的游戏术语/状态词（都是独立概念）
    common_game_terms = {
        'permanent', 'temporary', 'exploration', 'event', 'duration',
        'active', 'inactive', 'available', 'unavailable', 'complete',
        'incomplete', 'locked', 'unlocked', 'new', 'ongoing',
        'recurring', 'combat', 'leisure', 'challenge', 'remaining'
    }
    
    # 常见的标签关键词（冒号前面的部分）
    label_keywords = {
        'event', 'duration', 'time', 'remaining', 'status', 'type',
        'level', 'rank', 'tier', 'phase', 'stage', 'mode'
    }
    
    for text, conf in final_output:
        # 1. 检测冒号分隔（仅分割明确的标签：值格式）
        if ':' in text:
            parts = text.split(':', 1)
            if len(parts) == 2:
                before = parts[0].strip()
                after = parts[1].strip()
                before_words = len(before.split())
                after_words = len(after.split())
                
                # 检查是否是标签：值格式
                # 条件：1) 冒号前是1-3个词，2) 冒号前包含标签关键词，3) 冒号后是1-5个词
                is_label_format = (
                    1 <= before_words <= 3 and
                    1 <= after_words <= 5 and
                    any(keyword in before.lower() for keyword in label_keywords)
                )
                
                if is_label_format:
                    # 标签：值格式 → 分割
                    split_output.append((before, conf))
                    
                    # 如果值部分的第一个词是术语，单独输出
                    after_words_list = after.split()
                    if after_words_list and after_words_list[0].lower() in common_game_terms:
                        split_output.append((after_words_list[0], conf))
                        if len(after_words_list) > 1:
                            rest = ' '.join(after_words_list[1:])
                            split_output.append((rest, conf))
                    else:
                        split_output.append((after, conf))
                    continue
        
        # 2. 检测特殊符号分隔（如 "Permanent * Leisure"，星号是图标）
        if any(sep in text for sep in ['*', '|', '•', '◆', '★']):
            # 按这些符号分割
            import re
            parts = re.split(r'\s*[*|•◆★]\s*', text)
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) >= 2:
                # 不直接输出，而是将每个part放入待处理队列，继续检测
                # 这样可以处理 "Rekindled Duel Permanent * Leisure" → ["Rekindled Duel", "Permanent", "Leisure"]
                for part in parts:
                    # 检查这个part是否需要进一步分割（标题+标签组合）
                    part_words = part.split()
                    if len(part_words) >= 2 and not any(ch in part for ch in [',', '.', '!', '?', ':']):
                        last_word = part_words[-1]
                        if last_word.lower() in common_game_terms and last_word[0].isupper():
                            # 分离最后的术语词
                            title_part = ' '.join(part_words[:-1])
                            split_output.append((title_part, conf))
                            split_output.append((last_word, conf))
                            continue
                    # 否则直接输出
                    split_output.append((part, conf))
                continue
        
        # 3. 检测"标题 + 标签"组合（如 "Rekindled Duel Permanent"）
        # 策略：最后一个词如果是常见术语，将其单独分离
        words = text.split()
        if len(words) >= 2 and not any(ch in text for ch in [',', '.', '!', '?', ':']):
            last_word = words[-1]
            if last_word.lower() in common_game_terms and last_word[0].isupper():
                # 最后一词是标签术语 → 分离
                title_part = ' '.join(words[:-1])
                split_output.append((title_part, conf))
                split_output.append((last_word, conf))
                continue
        
        # 4. 检测空格分隔的多个术语（如 "Permanent Exploration"）
        # 只有当所有词都是常见游戏术语时才完全分割
        if len(words) == 2 and not any(ch in text for ch in [',', '.', '!', '?', ':']):
            all_capitalized = all(w[0].isupper() for w in words if w)
            both_common = all(w.lower() in common_game_terms for w in words)
            
            if all_capitalized and both_common:
                # 两个都是常见术语 → 完全分割
                for word in words:
                    split_output.append((word, conf))
                continue
        
        # 默认保持不分割
        split_output.append((text, conf))
    
    return split_output

