from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol
import threading
import time

from ludiglot.core.capture import CaptureRegion
from ludiglot.core.capture_match_workflow import (
    CaptureProcessCallbacks,
    CaptureProcessRequest,
    run_capture_match_workflow,
)


class CaptureAdapter(Protocol):
    def capture_desktop_snapshot(self) -> Any:
        ...

    def select_region(self, snapshot: Any | None = None) -> CaptureRegion | None:
        ...

    def capture_image_to_memory(self, selected_region: CaptureRegion | None, snapshot: Any | None = None) -> Any:
        ...


@dataclass(frozen=True)
class CaptureSessionCallbacks:
    status: Callable[[str], None]
    log: Callable[[str], None]
    error: Callable[[str], None]
    result: Callable[[dict[str, Any]], None]


ThreadStarter = Callable[[Callable[[], None]], None]
WorkflowRunner = Callable[[CaptureProcessRequest, CaptureProcessCallbacks], Any]


def start_daemon_thread(target: Callable[[], None]) -> None:
    threading.Thread(target=target, daemon=True).start()


class OverlayCaptureSession:
    def __init__(
        self,
        *,
        config_provider: Callable[[], Any],
        ocr_engine_provider: Callable[[], Any],
        matcher_provider: Callable[[], Any],
        capture_adapter: CaptureAdapter,
        callbacks: CaptureSessionCallbacks,
        stop_audio: Callable[[bool], None],
        clear_result_audio_state: Callable[[], None],
        thread_starter: ThreadStarter = start_daemon_thread,
        workflow_runner: WorkflowRunner = run_capture_match_workflow,
    ) -> None:
        self._config_provider = config_provider
        self._ocr_engine_provider = ocr_engine_provider
        self._matcher_provider = matcher_provider
        self._capture_adapter = capture_adapter
        self._callbacks = callbacks
        self._stop_audio = stop_audio
        self._clear_result_audio_state = clear_result_audio_state
        self._thread_starter = thread_starter
        self._workflow_runner = workflow_runner
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def trigger(self, force_select: bool = False) -> None:
        if self._running:
            self._callbacks.log("[HOTKEY] 正在处理中，忽略重复触发")
            return
        self._running = True
        t_start = time.time()
        selected_region: CaptureRegion | None = None
        snapshot: Any | None = None
        thread_started = False
        try:
            # 新一轮 OCR 前先停止当前播放，避免旧音频与新结果串音
            self._stop_audio(False)
            self._clear_result_audio_state()
            self._callbacks.log("[HOTKEY] 触发捕获")
            config = self._config_provider()
            if force_select or getattr(config, "capture_mode", None) == "select":
                self._callbacks.status("冻结屏幕…")
                t_snap_start = time.time()
                try:
                    snapshot = self._capture_adapter.capture_desktop_snapshot()
                except Exception as exc:
                    snapshot = None
                    self._callbacks.log(f"[CAPTURE] 预截图失败，回退实时框选: {exc}")
                t_snap_end = time.time()
                if snapshot is not None:
                    self._callbacks.log(f"[PERF] 屏幕快照耗时: {(t_snap_end - t_snap_start):.3f}s")
                self._callbacks.status("请选择 OCR 区域…")
                t_select_start = time.time()
                selected_region = self._capture_adapter.select_region(snapshot)
                t_select_end = time.time()
                self._callbacks.log(f"[PERF] 区域选择耗时: {(t_select_end - t_select_start):.3f}s")
                if selected_region is None:
                    self._callbacks.status("已取消")
                    return

            self._thread_starter(lambda: self._run_worker(selected_region, snapshot))
            thread_started = True
            self._callbacks.log(f"[PERF] 异步调用总耗时: {(time.time() - t_start):.3f}s")
        except Exception as exc:
            self._callbacks.log(f"[CAPTURE] 触发捕获异常: {exc}")
            self._callbacks.status("捕获失败")
        finally:
            # 仅在未成功启动后台线程时（后台线程会自己清除标志）清除
            if not thread_started:
                self._running = False

    def _run_worker(self, selected_region: CaptureRegion | None, snapshot: Any | None) -> None:
        try:
            self._run_workflow(selected_region, snapshot)
        finally:
            self._running = False

    def _run_workflow(self, selected_region: CaptureRegion | None, snapshot: Any | None) -> None:
        config = self._config_provider()
        self._workflow_runner(
            CaptureProcessRequest(
                capture_image=lambda: self._capture_adapter.capture_image_to_memory(selected_region, snapshot),
                ocr_engine=self._ocr_engine_provider(),
                matcher=self._matcher_provider(),
                ocr_backend=getattr(config, "ocr_backend", "auto"),
                debug_dump_input=getattr(config, "ocr_debug_dump_input", False),
                debug_dump_dir=config.image_path.parent if getattr(config, "image_path", None) else Path.cwd(),
            ),
            CaptureProcessCallbacks(
                status=self._callbacks.status,
                log=self._callbacks.log,
                error=self._callbacks.error,
                result=self._callbacks.result,
            ),
        )
