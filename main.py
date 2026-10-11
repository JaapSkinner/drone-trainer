import os
import sys
import logging
from PyQt5.QtWidgets import QApplication, QSplashScreen
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt
from services.app_logging import configure_logging
from services.paths import APP_ROOT
from ui.main_window import MainWindow

def main():
    # Asset paths (icons, stylesheets, meshes) are relative to the app root.
    os.chdir(APP_ROOT)
    configure_logging(level=logging.INFO)
    app = QApplication(sys.argv)

    # Show splash screen
    splash_pix = QPixmap('ui/assets/splashscreen.png')
    splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
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
