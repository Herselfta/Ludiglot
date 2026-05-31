from types import SimpleNamespace

import pytest

from ludiglot.core.capture import CaptureRegion
from ludiglot.ui.capture_session import CaptureSessionCallbacks, OverlayCaptureSession


class FakeCaptureAdapter:
    def __init__(self):
        self.snapshot = object()
        self.selected_region = CaptureRegion(1, 2, 3, 4)
        self.snapshot_error = None
        self.snapshot_calls = 0
        self.select_calls = []
        self.capture_calls = []

    def capture_desktop_snapshot(self):
        self.snapshot_calls += 1
        if self.snapshot_error:
            raise self.snapshot_error
        return self.snapshot

    def select_region(self, snapshot=None):
        self.select_calls.append(snapshot)
        return self.selected_region

    def capture_image_to_memory(self, selected_region, snapshot=None):
        self.capture_calls.append((selected_region, snapshot))
        return "image"


class ImmediateThreadStarter:
    def __init__(self):
        self.targets = []

    def __call__(self, target):
        self.targets.append(target)
        target()


class DeferredThreadStarter:
    def __init__(self):
        self.targets = []

    def __call__(self, target):
        self.targets.append(target)

    def run_next(self):
        self.targets.pop(0)()


def make_config(**overrides):
    data = {
        "capture_mode": "window",
        "ocr_backend": "auto",
        "ocr_debug_dump_input": False,
        "image_path": None,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def make_session(config=None, adapter=None, thread_starter=None, workflow_runner=None):
    events = []
    config_obj = config or make_config()
    adapter = adapter or FakeCaptureAdapter()
    thread_starter = thread_starter or ImmediateThreadStarter()

    def default_workflow(request, callbacks):
        callbacks.status("workflow-status")
        return request.capture_image()

    session = OverlayCaptureSession(
        config_provider=lambda: config_obj,
        ocr_engine_provider=lambda: "engine",
        matcher_provider=lambda: "matcher",
        capture_adapter=adapter,
        callbacks=CaptureSessionCallbacks(
            status=lambda value: events.append(("status", value)),
            log=lambda value: events.append(("log", value)),
            error=lambda value: events.append(("error", value)),
            result=lambda value: events.append(("result", value)),
        ),
        stop_audio=lambda emit_status: events.append(("stop_audio", emit_status)),
        clear_result_audio_state=lambda: events.append(("clear", None)),
        thread_starter=thread_starter,
        workflow_runner=workflow_runner or default_workflow,
    )
    return session, adapter, thread_starter, events


def test_trigger_ignores_duplicate_capture():
    thread_starter = DeferredThreadStarter()
    session, adapter, _, events = make_session(thread_starter=thread_starter)

    session.trigger()
    session.trigger()

    assert session.is_running is True
    assert len(thread_starter.targets) == 1
    assert adapter.snapshot_calls == 0
    assert ("log", "[HOTKEY] 正在处理中，忽略重复触发") in events


def test_direct_capture_starts_worker_without_selection():
    session, adapter, _, events = make_session(config=make_config(capture_mode="window"))

    session.trigger()

    assert session.is_running is False
    assert adapter.snapshot_calls == 0
    assert adapter.select_calls == []
    assert adapter.capture_calls == [(None, None)]
    assert ("stop_audio", False) in events
    assert ("clear", None) in events


def test_select_capture_uses_snapshot_then_selection():
    session, adapter, _, events = make_session(config=make_config(capture_mode="select"))

    session.trigger()

    assert adapter.snapshot_calls == 1
    assert adapter.select_calls == [adapter.snapshot]
    assert adapter.capture_calls == [(adapter.selected_region, adapter.snapshot)]
    assert ("status", "冻结屏幕…") in events
    assert ("status", "请选择 OCR 区域…") in events


def test_force_select_overrides_config_mode():
    session, adapter, _, _ = make_session(config=make_config(capture_mode="window"))

    session.trigger(force_select=True)

    assert adapter.snapshot_calls == 1
    assert adapter.select_calls == [adapter.snapshot]
    assert adapter.capture_calls == [(adapter.selected_region, adapter.snapshot)]


def test_snapshot_failure_falls_back_to_realtime_selection():
    adapter = FakeCaptureAdapter()
    adapter.snapshot_error = RuntimeError("boom")
    session, adapter, _, events = make_session(config=make_config(capture_mode="select"), adapter=adapter)

    session.trigger()

    assert adapter.select_calls == [None]
    assert adapter.capture_calls == [(adapter.selected_region, None)]
    assert ("log", "[CAPTURE] 预截图失败，回退实时框选: boom") in events


def test_selection_cancel_resets_running_and_does_not_start_worker():
    adapter = FakeCaptureAdapter()
    adapter.selected_region = None
    thread_starter = DeferredThreadStarter()
    session, adapter, _, events = make_session(
        config=make_config(capture_mode="select"),
        adapter=adapter,
        thread_starter=thread_starter,
    )

    session.trigger()

    assert session.is_running is False
    assert thread_starter.targets == []
    assert adapter.capture_calls == []
    assert ("status", "已取消") in events


def test_workflow_callbacks_are_forwarded():
    def workflow(request, callbacks):
        callbacks.status("status-from-workflow")
        callbacks.log("log-from-workflow")
        callbacks.error("error-from-workflow")
        callbacks.result({"ok": True})

    session, _, _, events = make_session(workflow_runner=workflow)

    session.trigger()

    assert ("status", "status-from-workflow") in events
    assert ("log", "log-from-workflow") in events
    assert ("error", "error-from-workflow") in events
    assert ("result", {"ok": True}) in events


def test_workflow_capture_image_uses_adapter_with_selected_region_and_snapshot():
    adapter = FakeCaptureAdapter()

    def workflow(request, callbacks):
        assert request.capture_image() == "image"

    session, adapter, _, _ = make_session(
        config=make_config(capture_mode="select"),
        adapter=adapter,
        workflow_runner=workflow,
    )

    session.trigger()

    assert adapter.capture_calls == [(adapter.selected_region, adapter.snapshot)]


def test_worker_finally_resets_running_after_exception():
    thread_starter = DeferredThreadStarter()

    def workflow(request, callbacks):
        raise RuntimeError("workflow failed")

    session, _, _, _ = make_session(thread_starter=thread_starter, workflow_runner=workflow)

    session.trigger()
    assert session.is_running is True

    with pytest.raises(RuntimeError, match="workflow failed"):
        thread_starter.run_next()

    assert session.is_running is False
