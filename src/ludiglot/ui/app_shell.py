from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ludiglot.core.config import load_config
from ludiglot.ui.overlay_window import OverlayWindow


def run_gui(config_path: Path) -> None:
    app = QApplication([])
    app.setFont(QFont("Segoe UI", 10))
    app.setQuitOnLastWindowClosed(False)

    try:
        config = load_config(config_path)
    except Exception as e:
        # 在终端显示错误信息，不使用GUI窗口
        print("\n" + "="*70)
        print("❌ Ludiglot 启动失败")
        print("="*70)
        print("\n加载配置或数据失败：")
        print(f"\n{e}")
        print("\n" + "="*70 + "\n")
        return

    window = OverlayWindow(config, config_path)
    window.hide()

    tray = QSystemTrayIcon(app)
    style = app.style()
    if style:
        tray.setIcon(style.standardIcon(style.StandardPixmap.SP_ComputerIcon))

    menu = QMenu()
    # 修复：明确 Show/Hide 的职责，不再使用 toggle，解决状态不一致导致的“双击才能显示”问题
    show_action = menu.addAction("Show")
    hide_action = menu.addAction("Hide")
    menu.addSeparator()
    capture_action = menu.addAction("Capture")
    reset_action = menu.addAction("Reset Window Position")
    quit_action = menu.addAction("Quit")

    if show_action:
        show_action.triggered.connect(window.show_and_activate)
    if hide_action:
        hide_action.triggered.connect(window.hide)
    if capture_action:
        capture_action.triggered.connect(lambda: window.capture_requested.emit(True))
    if reset_action:
        reset_action.triggered.connect(window.reset_window_position)
    if quit_action:
        quit_action.triggered.connect(app.quit)

    tray.setContextMenu(menu)
    # 单击图标切换显示/隐藏
    tray.activated.connect(lambda reason: window._toggle_visibility() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    # 双击图标触发捕获
    tray.activated.connect(lambda reason: window.capture_requested.emit(True) if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
    tray.show()

    print("[DEBUG] Entering app.exec()", flush=True)
    try:
        ret = app.exec()
        print(f"[DEBUG] app.exec() returned with {ret}", flush=True)
    except Exception as e:
        print(f"[ERROR] Exception in app.exec(): {e}", flush=True)
    finally:
        print("[DEBUG] Application exiting.", flush=True)
