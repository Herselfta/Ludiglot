from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import mss

try:
    import win32gui
except Exception:  # pragma: no cover
    win32gui = None


@dataclass
class CaptureRegion:
    left: int
    top: int
    width: int
    height: int


class CaptureError(RuntimeError):
    pass


def _save_grab(grab, out_path: Path) -> None:
    import mss.tools

    out_path.parent.mkdir(parents=True, exist_ok=True)
    mss.tools.to_png(grab.rgb, grab.size, output=str(out_path))


def capture_region(region: CaptureRegion, out_path: Path) -> None:
    print(f"[CAPTURE] 区域: L={region.left}, T={region.top}, W={region.width}, H={region.height}")
    with mss.mss() as sct:
        monitor = {
            "left": region.left,
            "top": region.top,
            "width": region.width,
            "height": region.height,
        }
        grab = sct.grab(monitor)
        _save_grab(grab, out_path)


def capture_fullscreen(out_path: Path, monitor_index: int = 1) -> None:
    with mss.mss() as sct:
        monitor = sct.monitors[monitor_index]
        grab = sct.grab(monitor)
        _save_grab(grab, out_path)


def _find_window_rect(title: str) -> Optional[tuple[int, int, int, int]]:
    if win32gui is None:
        raise CaptureError("缺少 pywin32，无法通过窗口标题截取")

    hwnd = win32gui.FindWindow(None, title)
    if hwnd == 0:
        return None
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    return left, top, right, bottom


def capture_window(title: str, out_path: Path, trim_borders: bool = True) -> None:
    rect = _find_window_rect(title)
    if rect is None:
        raise CaptureError(f"未找到窗口: {title}")

    left, top, right, bottom = rect
    if trim_borders:
        # 简单扣掉边框（经验值），可后续配置化
        left += 8
        top += 30
        right -= 8
        bottom -= 8

    region = CaptureRegion(left=left, top=top, width=right - left, height=bottom - top)
    capture_region(region, out_path)
