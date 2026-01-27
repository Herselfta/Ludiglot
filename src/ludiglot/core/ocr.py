from __future__ import annotations

import os
import shutil
import threading
import io
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union, cast

try:
    import numpy as np
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    Image = None
    np = None

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
            if self.lang.startswith("en"):
                lang = Language("en-US")
                self._windows_ocr = OcrEngine.try_create_from_language(lang)
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
        self._init_windows_ocr()
        if self._windows_ocr is None:
            return []
        
        # 在独立线程中执行以避免 STA 问题
        result_container = {"lines": [], "error": None}
        
        def _ocr_worker():
            try:
                from winrt.windows.storage.streams import InMemoryRandomAccessStream, DataWriter
                from winrt.windows.graphics.imaging import BitmapDecoder
            except ImportError:
                result_container["error"] = "WinRT模块导入失败"
                return
            except Exception as e:
                result_container["error"] = f"模块导入错误 - {e.__class__.__name__}"
                return

            try:
                # 读取图片并转换为 WinRT 可用的格式
                data = Path(image_path).read_bytes()
                stream = InMemoryRandomAccessStream()
                writer = DataWriter(stream)
                writer.write_bytes(data)
                writer.store_async().get()
                writer.flush_async().get()
                writer.detach_stream()
                stream.seek(0)
                
                # 解码图片
                decoder = BitmapDecoder.create_async(stream).get()
                bitmap = decoder.get_software_bitmap_async().get()
                
                # 执行 OCR
                result = self._windows_ocr.recognize_async(bitmap).get()
                
                if not result or not getattr(result, "lines", None):
                    return
                
                # 解析识别结果
                for line in result.lines:
                    text = getattr(line, "text", "") or ""
                    if not text.strip():
                        continue
                    
                    # Windows OCR的坐标信息在words中
                    words = getattr(line, "words", None)
                    if not words or len(list(words)) == 0:
                        box = [[0, 0], [100, 0], [100, 30], [0, 30]]
                        result_container["lines"].append({"text": text.strip(), "conf": 0.92, "box": box})
                        continue
                    
                    # 收集单词级别的坐标，检测独立元素
                    word_list = []
                    for word in words:
                        word_text = getattr(word, "text", "").strip()
                        rect = getattr(word, "bounding_rect", None)
                        if not word_text or not rect:
                            continue
                        word_list.append({
                            "text": word_text,
                            "x": rect.x,
                            "y": rect.y,
                            "width": rect.width,
                            "height": rect.height
                        })
                    
                    if not word_list:
                        box = [[0, 0], [100, 0], [100, 30], [0, 30]]
                        result_container["lines"].append({"text": text.strip(), "conf": 0.92, "box": box})
                        continue
                    
                    # 检测独立元素（X间距过大）
                    groups = []
                    current_group = [word_list[0]]
                    
                    for i in range(1, len(word_list)):
                        prev_word = word_list[i-1]
                        curr_word = word_list[i]
                        # 计算间距
                        gap = curr_word["x"] - (prev_word["x"] + prev_word["width"])
                        # 如果间距 > 50px，认为是独立元素
                        if gap > 50:
                            groups.append(current_group)
                            current_group = [curr_word]
                        else:
                            current_group.append(curr_word)
                    groups.append(current_group)
                    
                    # 每组输出一个条目
                    for group in groups:
                        group_text = " ".join([w["text"] for w in group])
                        min_x = min(w["x"] for w in group)
                        min_y = min(w["y"] for w in group)
                        max_x = max(w["x"] + w["width"] for w in group)
                        max_y = max(w["y"] + w["height"] for w in group)
                        box = [
                            [int(min_x), int(min_y)],
                            [int(max_x), int(min_y)],
                            [int(max_x), int(max_y)],
                            [int(min_x), int(max_y)],
                        ]
                        result_container["lines"].append({"text": group_text, "conf": 0.92, "box": box})
                    
            except Exception as e:
                result_container["error"] = f"{e.__class__.__name__}: {str(e)[:100]}"
        
        # 在新线程中执行OCR
        thread = threading.Thread(target=_ocr_worker, daemon=True)
        thread.start()
        thread.join(timeout=10.0)  # 最多等待10秒
        
        if thread.is_alive():
            print("[OCR] Windows OCR 超时")
            return []
        
        if result_container["error"]:
            print(f"[OCR] Windows OCR 识别失败：{result_container['error']}")
            return []
        
        lines = result_container["lines"]
        if lines:
            print(f"[OCR] Windows OCR 成功识别 {len(lines)} 行文本")
        return lines

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
        
        def _ocr_worker():
            try:
                from winrt.windows.storage.streams import InMemoryRandomAccessStream, DataWriter
                from winrt.windows.graphics.imaging import BitmapDecoder
            except ImportError:
                result_container["error"] = "WinRT模块导入失败"
                return
            except Exception as e:
                result_container["error"] = f"模块导入错误 - {e.__class__.__name__}"
                return

            try:
                # 直接从内存字节流创建 WinRT 流
                stream = InMemoryRandomAccessStream()
                writer = DataWriter(stream)
                writer.write_bytes(image_bytes)
                writer.store_async().get()
                writer.flush_async().get()
                writer.detach_stream()
                stream.seek(0)
                
                # 解码图片
                decoder = BitmapDecoder.create_async(stream).get()
                bitmap = decoder.get_software_bitmap_async().get()
                
                # 执行 OCR
                if not self._windows_ocr:
                    result_container["error"] = "Windows OCR未初始化"
                    return
                result = self._windows_ocr.recognize_async(bitmap).get()
                
                if not result or not getattr(result, "lines", None):
                    return
                
                # 解析识别结果（同样的逻辑）
                for line in result.lines:
                    text = getattr(line, "text", "") or ""
                    if not text.strip():
                        continue
                    
                    words = getattr(line, "words", None)
                    if not words or len(list(words)) == 0:
                        box = [[0, 0], [100, 0], [100, 30], [0, 30]]
                        result_container["lines"].append({"text": text.strip(), "conf": 0.92, "box": box})
                        continue
                    
                    # 计算整行的边界框
                    min_x, min_y = float('inf'), float('inf')
                    max_x, max_y = 0, 0
                    for word in words:
                        rect = getattr(word, "bounding_rect", None)
                        if rect:
                            min_x = min(min_x, rect.x)
                            min_y = min(min_y, rect.y)
                            max_x = max(max_x, rect.x + rect.width)
                            max_y = max(max_y, rect.y + rect.height)
                    
                    if min_x != float('inf'):
                        box = [
                            [int(min_x), int(min_y)],
                            [int(max_x), int(min_y)],
                            [int(max_x), int(max_y)],
                            [int(min_x), int(max_y)],
                        ]
                    else:
                        box = [[0, 0], [100, 0], [100, 30], [0, 30]]
                    
                    result_container["lines"].append({"text": text.strip(), "conf": 0.92, "box": box})
                    
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


def group_ocr_lines(box_lines: List[Dict[str, object]]) -> List[Tuple[str, float]]:
    """将 OCR 结果按坐标分行，并按从上到下、从左到右拼接为行文本。
    
    智能分组策略：
    1. 基本分行：按y坐标中心距离判断是否同一行
    2. 对话模式：识别"标题+多行内容"模式，自动合并对话行
    3. 二次分割：按冒号、特殊符号等分隔符进一步拆分
    """
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
        items.append({"text": text, "conf": conf, "x1": x1, "y1": y1, "cy": cy, "h": h})

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
        threshold = max(12.0, float(current_h) * 0.7)
        if current_y is not None and abs(cast(float, item["cy"]) - current_y) <= threshold:
            current.append(item)
            # 更新行中心
            current_y = (current_y + cast(float, item["cy"])) / 2.0
            current_h = max(float(current_h), cast(float, item["h"]))
        else:
            lines.append(current)
            current = [item]
            current_y = cast(float, item["cy"])
            current_h = cast(float, item["h"])
    if current:
        lines.append(current)

    # 构建初步输出
    initial_output: List[Tuple[str, float, bool]] = []  # (text, conf, is_title_like)
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
                # 计算X间距
                gap = cast(float, item["x1"]) - (cast(float, prev_item["x1"]) + 100)  # 假设元素宽度~100px
                # 如果间距 > 40px，认为是独立元素
                if gap > 40:
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
            is_title = word_count <= 3 and char_count <= 30 and not is_likely_sentence
            
            initial_output.append((text, avg_conf, is_title, group_y, group_h))
    
    # 智能合并：识别并合并段落
    # 策略：连续的短标题保持独立，连续的长文本合并为段落
    # 重要：检测Y坐标间隔，分离不连续的段落
    final_output: List[Tuple[str, float]] = []
    
    if len(initial_output) >= 1:
        # 扫描并分组：标题组 vs 内容组
        i = 0
        while i < len(initial_output):
            text, conf, is_title, y, h = initial_output[i]
            
            if is_title:
                # 短标题行：检查下一行是否也是标题
                title_group = [initial_output[i]]
                i += 1
                # 最多合并2个连续的短标题（如：标题第1行 + 标题第2行）
                if i < len(initial_output) and initial_output[i][2] and len(title_group) < 2:
                    title_group.append(initial_output[i])
                    i += 1
                
                # 输出标题（如果是2行，用空格连接）
                if len(title_group) == 1:
                    final_output.append((title_group[0][0], title_group[0][1]))
                else:
                    # 合并2行标题
                    merged_title = " ".join([t[0] for t in title_group])
                    avg_conf = sum(t[1] for t in title_group) / len(title_group)
                    final_output.append((merged_title, avg_conf))
            else:
                # 长内容行：收集连续且Y坐标紧密的非标题行
                content_group = [initial_output[i]]
                prev_y_bottom = y + h  # 当前行的底部Y坐标
                prev_h = h
                i += 1
                
                while i < len(initial_output) and not initial_output[i][2]:
                    next_text, next_conf, next_is_title, next_y, next_h = initial_output[i]
                    # 计算Y间隔
                    y_gap = next_y - prev_y_bottom
                    
                    # 检测段落分隔的两种情况：
                    # 1. Y间隔 > 1.5倍行高（视觉分段）
                    # 2. 前一行以句号结尾 且 Y间隔 > 0.5倍行高（语义分段）
                    prev_text = content_group[-1][0]
                    is_visual_gap = y_gap > prev_h * 1.5
                    is_semantic_gap = prev_text.rstrip().endswith('.') and y_gap > prev_h * 0.5
                    
                    if is_visual_gap or is_semantic_gap:
                        break  # 停止合并，开始新段落
                    content_group.append(initial_output[i])
                    prev_y_bottom = next_y + next_h
                    prev_h = next_h
                    i += 1
                
                # 合并当前段落
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

