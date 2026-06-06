from __future__ import annotations

import threading
from typing import Any, Callable

from ludiglot.ui.hotkey_registrar import HotkeyBinding

ThreadStarter = Callable[[Callable[[], None]], None]


def start_daemon_thread(target: Callable[[], None]) -> None:
    threading.Thread(target=target, daemon=True).start()


def convert_hotkey_for_pynput(hotkey: str) -> str:
    key = hotkey.lower().replace("ctrl", "<ctrl>").replace("shift", "<shift>")
    key = key.replace("alt", "<alt>").replace("win", "<cmd>")
    return key


class PynputHotkeyRegistration:
    def __init__(self, listener: Any) -> None:
        self._listener = listener
        self._stopped = False

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        stop = getattr(self._listener, "stop", None)
        if stop is not None:
            stop()


class PynputGlobalHotkeyAdapter:
    name = "pynput"

    def __init__(
        self,
        *,
        keyboard_provider: Callable[[], Any] | None = None,
        thread_starter: ThreadStarter = start_daemon_thread,
    ) -> None:
        self._keyboard_provider = keyboard_provider or self._default_keyboard_provider
        self._thread_starter = thread_starter

    def register(self, bindings: tuple[HotkeyBinding, ...]) -> PynputHotkeyRegistration | None:
        keyboard = self._keyboard_provider()
        pynput_bindings = {
            convert_hotkey_for_pynput(binding.hotkey): binding.callback
            for binding in bindings
        }
        listener = keyboard.GlobalHotKeys(pynput_bindings)
        self._thread_starter(listener.run)
        return PynputHotkeyRegistration(listener)

    def _default_keyboard_provider(self) -> Any:
        from pynput import keyboard

        return keyboard
