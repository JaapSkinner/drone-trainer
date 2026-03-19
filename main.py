import sys
from PyQt5.QtWidgets import QApplication, QSplashScreen
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt
from OpenGL.GLUT import glutInit
from ui.main_window import MainWindow
# from services.vicon_connection import ViconConnection

def main():
    glutInit(sys.argv)
    import logging
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(name)s: %(message)s')
    app = QApplication(sys.argv)

    # Show splash screen
    splash_pix = QPixmap('ui/assets/splashscreen.png')
    splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()

    # vicon = ViconConnection('192.168.10.1', 'mug')
    main_window = MainWindow()

    main_window.show()
    main_window.raise_()
    main_window.activateWindow()

    # Ensure services are cleaned up on application quit even if the
    # window isn't explicitly closed — this avoids QThreads being
    # destroyed while still running.
    app.aboutToQuit.connect(main_window.close)

    splash.finish(main_window)
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
