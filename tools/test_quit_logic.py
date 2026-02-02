import sys
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import QTimer

def run():
    print("Creating App...")
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    
    print("Creating Hidden Window...")
    w1 = QWidget()
    w1.hide()
    
    print("Creating Visible Window...")
    w2 = QWidget()
    w2.show()
    
    def close_w2():
        print("Closing Visible Window...")
        w2.close()
        # Schedule a check
        QTimer.singleShot(1000, check_alive)

    def check_alive():
        print("App is still alive after closing visible window!")
        app.quit()

    QTimer.singleShot(1000, close_w2)
    
    print(" entering exec()")
    app.exec()
    print(" exec() finished.")

if __name__ == "__main__":
    run()
