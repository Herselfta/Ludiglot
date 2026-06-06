from __future__ import annotations

from types import SimpleNamespace

from ludiglot.ui.hotkey_registrar import HotkeyRegistrar, HotkeyRegistrarCallbacks


class FakeRegistration:
    def __init__(self) -> None:
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1


class FakeAdapter:
    name = "fake"

    def __init__(self, registration=None, error: Exception | None = None) -> None:
        self.registration = registration
        self.error = error
        self.calls = []

    def register(self, bindings):
        self.calls.append(bindings)
        if self.error is not None:
            raise self.error
        return self.registration


def make_callbacks(events: list[str], logs: list[str], errors: list[str]) -> HotkeyRegistrarCallbacks:
    return HotkeyRegistrarCallbacks(
        capture=lambda: events.append("capture"),
        toggle=lambda: events.append("toggle"),
        log=logs.append,
        error=errors.append,
    )


def make_config(capture="ctrl+shift+o", toggle=None):
    return SimpleNamespace(hotkey_capture=capture, hotkey_toggle=toggle)


def test_start_without_capture_hotkey_does_nothing():
    events: list[str] = []
    logs: list[str] = []
    errors: list[str] = []
    primary = FakeAdapter(FakeRegistration())
    fallback = FakeAdapter(FakeRegistration())
    registrar = HotkeyRegistrar(
        config_provider=lambda: make_config(capture="", toggle="alt+h"),
        callbacks=make_callbacks(events, logs, errors),
        primary_adapter=primary,
        fallback_adapter=fallback,
    )

    registrar.start()

    assert primary.calls == []
    assert fallback.calls == []
    assert logs == []
    assert errors == []


def test_start_registers_native_hotkeys_first():
    events: list[str] = []
    logs: list[str] = []
    errors: list[str] = []
    native_registration = FakeRegistration()
    primary = FakeAdapter(native_registration)
    fallback = FakeAdapter(FakeRegistration())
    registrar = HotkeyRegistrar(
        config_provider=lambda: make_config(),
        callbacks=make_callbacks(events, logs, errors),
        primary_adapter=primary,
        fallback_adapter=fallback,
    )

    registrar.start()

    assert len(primary.calls) == 1
    assert fallback.calls == []
    assert logs == ["[HOTKEY] 已注册(WinAPI): ctrl+shift+o"]
    assert errors == []


def test_start_includes_toggle_when_configured():
    events: list[str] = []
    logs: list[str] = []
    errors: list[str] = []
    primary = FakeAdapter(FakeRegistration())
    registrar = HotkeyRegistrar(
        config_provider=lambda: make_config(capture="alt+w", toggle="alt+h"),
        callbacks=make_callbacks(events, logs, errors),
        primary_adapter=primary,
    )

    registrar.start()

    bindings = primary.calls[0]
    assert [(binding.name, binding.hotkey) for binding in bindings] == [("capture", "alt+w"), ("toggle", "alt+h")]
    assert logs == ["[HOTKEY] 已注册(WinAPI): alt+w / alt+h"]


def test_native_failure_falls_back_to_pynput():
    events: list[str] = []
    logs: list[str] = []
    errors: list[str] = []
    primary = FakeAdapter(None)
    fallback = FakeAdapter(FakeRegistration())
    registrar = HotkeyRegistrar(
        config_provider=lambda: make_config(capture="alt+w", toggle="alt+h"),
        callbacks=make_callbacks(events, logs, errors),
        primary_adapter=primary,
        fallback_adapter=fallback,
    )

    registrar.start()

    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1
    assert logs == ["[HOTKEY] 已注册: alt+w / alt+h"]
    assert errors == []


def test_fallback_import_error_reports_global_hotkey_unavailable():
    events: list[str] = []
    logs: list[str] = []
    errors: list[str] = []
    primary = FakeAdapter(None)
    fallback = FakeAdapter(error=ImportError("missing pynput"))
    registrar = HotkeyRegistrar(
        config_provider=lambda: make_config(),
        callbacks=make_callbacks(events, logs, errors),
        primary_adapter=primary,
        fallback_adapter=fallback,
    )

    registrar.start()

    assert errors == ["全局热键不可用: missing pynput"]
    assert logs == []


def test_stop_delegates_to_active_registration_and_is_idempotent():
    events: list[str] = []
    logs: list[str] = []
    errors: list[str] = []
    registration = FakeRegistration()
    registrar = HotkeyRegistrar(
        config_provider=lambda: make_config(),
        callbacks=make_callbacks(events, logs, errors),
        primary_adapter=FakeAdapter(registration),
    )

    registrar.start()
    registrar.stop()
    registrar.stop()

    assert registration.stop_calls == 1


def test_callbacks_are_preserved_in_bindings():
    events: list[str] = []
    logs: list[str] = []
    errors: list[str] = []
    primary = FakeAdapter(FakeRegistration())
    registrar = HotkeyRegistrar(
        config_provider=lambda: make_config(capture="alt+w", toggle="alt+h"),
        callbacks=make_callbacks(events, logs, errors),
        primary_adapter=primary,
    )

    registrar.start()
    bindings = primary.calls[0]
    {binding.name: binding.callback for binding in bindings}["capture"]()
    {binding.name: binding.callback for binding in bindings}["toggle"]()

    assert events == ["capture", "toggle"]
