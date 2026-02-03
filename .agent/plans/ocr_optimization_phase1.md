# IMPL PLAN: OCR Optimization Phase 1

## Goal
Fix critical coordinate scaling bugs and optimize the OCR data pipeline to reduce latency and disk I/O.

## Tasks

### 1. Fix Coordinate Scaling Bug in `src/ludiglot/core/ocr.py`
**Issue:** When adaptive scaling (Text-Grab strategy) is triggered (`scale > 1.0`), the returned bounding boxes are in the scaled coordinate system, causing UI misalignment.
**Fix:**
- In `_recognize_bytes` (or the worker method), when receiving results from the recursive call `_recognize_bytes(new_bytes)`, iterate over the returned lines/boxes and divide all coordinates by `scale`.

### 2. Implement In-Memory Capture in `src/ludiglot/core/capture.py`
**Issue:** Current capture logic forces saving to disk (`capture_region`, `capture_fullscreen`), reading back, then processing.
**Fix:**
- Add `capture_region_to_image(region) -> PIL.Image`
- Add `capture_fullscreen_to_image(monitor_index) -> PIL.Image`
- Use `mss` to grab bytes and create PIL Image directly.

### 3. Optimize OCR Engine Pipeline in `src/ludiglot/core/ocr.py`
**Issue:** `recognize_from_image` currently saves PIL image to a PNG byte stream (slow encoding) -> WinRT Stream -> BitmapDecoder -> SoftwareBitmap.
**Fix:**
- Refactor `recognize_from_image` to accept `PIL.Image`.
- Implement a fast path:
    - Convert PIL Image to BGRA8 raw bytes (`img.convert('RGBA')` then rearrange or `tobytes`).
    - Use `SoftwareBitmap.create_copy_from_buffer` if possible (requires efficient `IBuffer` creation from python bytes).
    - *Fallback/Safe Path*: If `IBuffer` interaction is complex/unstable in pure Python `winrt`, use `BMP` (uncompressed) format in `BytesIO` instead of PNG (compressed) to speed up `BitmapDecoder`.

### 4. Update UI to use In-Memory Pipeline `src/ludiglot/ui/overlay_window.py`
**Issue:** `overlay_window.py` relies on `self.config.image_path` (disk) for OCR.
**Fix:**
- In `_capture_and_process`, call the new `capture_..._to_image` methods.
- Pass the resulting `PIL.Image` directly to `self.engine.recognize_from_image`.
- Remove the intermediate `_preprocess_image` disk-IO steps.

## Verification
- Run `tools/test_extract_capture.py` (modified to check coordinates).
- Use `cache/capture.png` as a test case to ensure scaling logic works correctly (coordinates should match original image dimensions).
