import sys
import shutil
import time
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Add src to path
project_root = Path(__file__).resolve().parents[1]
sys.path.append(str(project_root / "src"))

from ludiglot.core.config import load_config
from ludiglot.ui.overlay_window import OverlayWindow
from ludiglot.core.capture import CaptureRegion

# Paths
TOOLS_DIR = project_root / "tools"
# Use one image that matches
TEST_IMAGE = TOOLS_DIR / "TestShortPlotAudio.png"
CONFIG_PATH = project_root / "config" / "settings.json"

def run_test():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False) # Key setting
    
    if not CONFIG_PATH.exists():
        print(f"Config path not found: {CONFIG_PATH}")
        sys.exit(1)

    # Load config and force play_audio
    config = load_config(CONFIG_PATH)
    config.play_audio = True
    config.capture_mode = "image"
    
    print("Starting Reproduction Test (Real AudioPlayer)...", flush=True)

    # Real Window, No Mocks
    window = OverlayWindow(config, CONFIG_PATH)
    window.show()

    def on_resources_loaded():
        print("Resources loaded. Triggering capture in 1s...", flush=True)
        QTimer.singleShot(1000, trigger_capture)

    def trigger_capture():
        print(f"Copying {TEST_IMAGE.name} to {config.image_path}", flush=True)
        shutil.copy(TEST_IMAGE, config.image_path)
        print("Triggering capture signal...", flush=True)
        window.capture_requested.emit(False)

    window.resources_loaded.connect(on_resources_loaded)

    # Watchdog to see if it stays alive
    def check_alive():
        print("App is still alive...", flush=True)
    
    timer = QTimer()
    timer.timeout.connect(check_alive)
    timer.start(2000)

    exit_code = app.exec()
    print(f"App exited with code: {exit_code}", flush=True)

if __name__ == "__main__":
    run_test()
