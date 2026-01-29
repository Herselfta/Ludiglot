import sys
import shutil
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src to path
project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root / "src"))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QObject

from ludiglot.core.config import load_config
from ludiglot.ui.overlay_window import OverlayWindow
from ludiglot.core.capture import CaptureRegion

# Paths
TOOLS_DIR = project_root / "tools"
TEST_IMAGES = [
    TOOLS_DIR / "TestShortPlotAudio.png",
    TOOLS_DIR / "TestLongPlotAudio.png",
    TOOLS_DIR / "TestFavorAudio.png",
]
CONFIG_PATH = project_root / "config" / "settings.json"

class MockOverlayWindow(OverlayWindow):
    def __init__(self, config, config_path):
        super().__init__(config, config_path)
        self.image_queue = list(TEST_IMAGES)

    def _capture_image(self, selected_region: CaptureRegion | None) -> None:
        if not self.image_queue:
            print("No more images to process.", flush=True)
            return

        src = self.image_queue.pop(0)
        print(f"Mocking capture with image: {src.name}", flush=True)
        shutil.copy(src, self.config.image_path)
        return 

class TestDriver(QObject):
    def __init__(self, window, mock_player):
        super().__init__()
        self.window = window
        self.mock_player = mock_player
        self.step = 0
        self.total_steps = len(TEST_IMAGES)
        
        # Connect signals for sequential execution
        self.window.signals.result.connect(self.on_result)
        self.window.signals.error.connect(self.on_error)
        
        # Safety timeout in case a step hangs (e.g. OCR fails silentish)
        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self.on_timeout)

    def start(self):
        # Wait a bit for window initialization
        QTimer.singleShot(2000, self.trigger_next)

    def trigger_next(self):
        if self.step < self.total_steps:
            print(f"\n[{self.step + 1}/{self.total_steps}] Triggering capture...", flush=True)
            self.mock_player.play.reset_mock()
            self.window.capture_requested.emit(False)
            # Start safety timer (30s per step should be plenty)
            self.timeout_timer.start(30000)
        else:
            print("\nAll images processed. Exiting.", flush=True)
            QApplication.instance().quit()

    def on_result(self, result):
        self.timeout_timer.stop()
        print("Received Processing Result.")
        
        # Verify Audio
        if self.mock_player.play.called:
             args = self.mock_player.play.call_args
             print(f"SUCCESS: Audio played: {args}", flush=True)
        else:
             print("FAILURE: Audio did not play.", flush=True)
        
        self.step += 1
        # Schedule next step
        QTimer.singleShot(2000, self.trigger_next)

    def on_error(self, err):
        self.timeout_timer.stop()
        print(f"Error occurred: {err}", flush=True)
        self.step += 1
        QTimer.singleShot(2000, self.trigger_next)

    def on_timeout(self):
        print("Step timed out! Moving to next.", flush=True)
        self.step += 1
        self.trigger_next()

def run_test():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    if not CONFIG_PATH.exists():
        print(f"Config path not found: {CONFIG_PATH}")
        sys.exit(1)

    # Load config and force play_audio
    config = load_config(CONFIG_PATH)
    config.play_audio = True
    config.capture_mode = "image"
    
    print("Starting Sequential Integration Test...", flush=True)

    # Setup Mock
    with patch('ludiglot.ui.overlay_window.AudioPlayer') as MockAudioPlayer:
        mock_player_instance = MockAudioPlayer.return_value
        # Mock is_playing to return False so logic proceeds
        mock_player_instance.is_playing.return_value = False
        
        window = MockOverlayWindow(config, CONFIG_PATH)
        window.player = mock_player_instance 
        window.show()

        driver = TestDriver(window, mock_player_instance)
        driver.start()

        app.exec()

if __name__ == "__main__":
    run_test()
