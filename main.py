import os
import sys
import logging
from PyQt5.QtWidgets import QApplication, QSplashScreen
from PyQt5.QtCore import Qt
from services.app_logging import configure_logging
from services.paths import APP_ROOT
from ui.main_window import MainWindow
from ui.splash import app_icon, splash_pixmap

def main():
    # Asset paths (icons, stylesheets, meshes) are relative to the app root.
    os.chdir(APP_ROOT)
    configure_logging(level=logging.INFO)
    # Crisp text and icons on high-DPI screens (must be set before the QApplication).
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("Drone Trainer")
    app.setWindowIcon(app_icon())

    # Show splash screen
    splash = QSplashScreen(splash_pixmap(app.devicePixelRatio()), Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
    splash.setAttribute(Qt.WA_TranslucentBackground)
    splash.show()
    app.processEvents()

    main_window = MainWindow()

    main_window.show()
    main_window.raise_()
    main_window.activateWindow()

    # Ensure services are cleaned up on application quit even if the
    # window isn't explicitly closed — this avoids QThreads being
    # destroyed while still running.
    app.aboutToQuit.connect(main_window.close)

    splash.finish(main_window)
    exit_code = app.exec_()
    # Destroy widgets before the QApplication; letting Python free them in
    # arbitrary order at interpreter exit can segfault.
    del main_window, splash
    sys.exit(exit_code)

if __name__ == '__main__':
    main()
