import sys
import subprocess
import time
import signal
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QFileSystemWatcher, QTimer

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # 支持 Ctrl+C 终止
    signal.signal(signal.SIGINT, lambda *a: app.quit())
    # 必须有定时器才能让Qt事件循环定期交出控制权给Python检查信号
    sig_timer = QTimer()
    sig_timer.timeout.connect(lambda: None)
    sig_timer.start(200)
    
    # 监控的 UI 目录
    ui_dir = Path(__file__).resolve().parents[1] / "src" / "ludiglot" / "ui"
    sandbox_script = Path(__file__).resolve().parent / "ui_sandbox.py"
    
    process = None
    
    def start_process():
        nonlocal process
        if process:
            try:
                process.terminate()
                process.wait(timeout=1)
            except Exception:
                process.kill()
        print("[I.R.I.S.] UI源码检测到变更，正在重启前端沙盒...")
        
        # 启动沙盒
        process = subprocess.Popen([sys.executable, str(sandbox_script)])

    watcher = QFileSystemWatcher()
    watcher.addPath(str(ui_dir))
    for f in ui_dir.rglob("*.py"):
        watcher.addPath(str(f))
        
    def on_change(path):
        # Debounce
        timer.start(300)

    watcher.fileChanged.connect(on_change)
    watcher.directoryChanged.connect(on_change)
    
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(start_process)
    
    print("[I.R.I.S.] 已启动前台UI热更新监听器. 监控目录:", ui_dir)
    start_process()
    
    # 防止父进程退出前孤儿子进程残留
    try:
        sys.exit(app.exec())
    finally:
        if process:
            process.kill()

if __name__ == "__main__":
    main()