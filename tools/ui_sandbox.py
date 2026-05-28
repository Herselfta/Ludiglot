import sys
import tempfile
from pathlib import Path

# ---------- MOCK HEAVY IMPORTS BEFORE IMPORTING UI ----------
import ludiglot.core.overlay_runtime as overlay_runtime
from dataclasses import dataclass

@dataclass
class MockResult:
    success: bool
    resources: any

class MockResources:
    db = {}
    matcher = None
    audio_resolver = None
    skill_param_resolver = None
    voice_map = {}
    voice_event_index = None
    audio_index = None
    external_wem_root = None

overlay_runtime.initialize_overlay_runtime = lambda *args, **kwargs: MockResult(success=True, resources=MockResources())
overlay_runtime.create_overlay_ocr_engine = lambda *args, **kwargs: None
# ------------------------------------------------------------

from PyQt6.QtWidgets import QApplication
from ludiglot.core.config import AppConfig
from ludiglot.ui.overlay_window import OverlayWindow, UiSignals
from ludiglot.core.audio_playback_orchestrator import AudioPlaybackIdentity

import time

class MockDecision:
    def __init__(self, identity):
        self.identity = identity
        self.action = "play"
        self.path = Path("mock/audio.wem")
        self.path = Path("mock/audio.wem")

class MockAudioPlayer:
    def __init__(self):
        self._is_playing = False
        self._start_time = 0
        self._duration_ms = 4730
        self._pause_time = 0

    def play(self, path: str, block: bool = False) -> None:
        self._is_playing = True
        self._start_time = time.time() - (self._pause_time if self._pause_time > 0 else 0)
        self._pause_time = 0

    def stop(self) -> None:
        self._is_playing = False
        self._start_time = 0
        self._pause_time = 0

    def pause(self) -> None:
        if self._is_playing:
            self._is_playing = False
            self._pause_time = time.time() - self._start_time

    def resume(self) -> None:
        if not self._is_playing:
            self._is_playing = True
            self._start_time = time.time() - self._pause_time

    def seek(self, position: float) -> None:
        self._start_time = time.time() - (position * (self._duration_ms / 1000.0))

    def is_playing(self) -> bool:
        return self._is_playing

    def get_position(self) -> float:
        if not self._is_playing and self._pause_time == 0:
            return 0.0
        
        elapsed = (time.time() - self._start_time) if self._is_playing else self._pause_time
        pos = elapsed / (self._duration_ms / 1000.0)
        if pos >= 1.0:
            self.stop()
            return 1.0
        return pos

    def get_duration(self) -> int:
        return self._duration_ms

class MockAudioRuntime:
    def __init__(self, *args, **kwargs):
        self.current_playback = None
        self.audio_index = None
        
    def resolve_intent(self, intent):
        return self.current_playback
        
    def prepare_playback(self, identity):
        if not self.current_playback:
            self.current_playback = identity
        return MockDecision(self.current_playback)
        
    def dispatch_playback(self, *args, **kwargs):
        pass
        
    def stop_all(self):
        pass


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Ludiglot Mock UI Runtime")
    app.setQuitOnLastWindowClosed(False)
    
    config = AppConfig(
        data_root=Path("."),
        en_json=Path("."),
        zh_json=Path("."),
        db_path=Path("."),
        image_path=Path("."),
        fonts_root=Path("."),
        font_en="Segoe UI",
        font_cn="Microsoft YaHei"
    )
    temp_config = Path(tempfile.gettempdir()) / "ludiglot_mock_config.json"
    if not temp_config.exists():
        temp_config.write_text("{}", encoding="utf-8")
    
    # Patch OverlayWindow to avoid real audio runtime
    original_apply = OverlayWindow._apply_runtime_resources
    def mocked_apply(self, resources):
        original_apply(self, resources)
        self.audio_runtime = MockAudioRuntime()
        self.player = MockAudioPlayer()
    OverlayWindow._apply_runtime_resources = mocked_apply

    window = OverlayWindow(config, temp_config)
    window.disable_auto_hide = True
    window.show()
    
    # Simulate a translation result appearing after window opens
    def inject_dummy_data():
        try:
            window.signals.status.emit("沙盒模式")
            
            text_en = "They didn't just \"get into\" our work. They went a step further—replacement."
            text_cn = "不止是介入，而是更进一步——替换。"
            
            # Simulate active audio
            if window.audio_runtime:
                window.audio_runtime.current_playback = AudioPlaybackIdentity(
                    text_key=None,
                    hash_value=2454200731,
                    event_name="HotReloadMockEvent",
                    source_type="Voice"
                )
                # simulate audio total time
                window.player.total_time = 4.73
                window.player._duration = 4.73
            
            window.signals.result.emit({
                "_query_key": "theydidntjustgetintoourworktheywentastepfurtherreplacement",
                "_score": 1.0,
                "matches": [
                    {
                        "official_en": text_en,
                        "official_cn": text_cn,
                        "text_key": "MAIN_RGLC_13_2",
                        "audio_hash": 2454200731,
                        "audio_event": "HotReloadMockEvent",
                    }
                ],
                "type": "Plot",
                "has_audio": True
            })
        except Exception:
            import traceback
            traceback.print_exc()

    def print_status():
        print(f"[STATUS] Window active: {window.isActiveWindow()}, visible: {window.isVisible()}, size: {window.size()}, pos: {window.pos()}")

    from PyQt6.QtCore import QTimer
    timer = QTimer(app)
    timer.setSingleShot(True)
    timer.timeout.connect(inject_dummy_data)
    timer.start(500)
    
    status_timer = QTimer(app)
    status_timer.timeout.connect(print_status)
    status_timer.start(1000)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()