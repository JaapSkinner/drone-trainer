import sys
from PyQt5.QtWidgets import QApplication
from OpenGL.GLUT import glutInit
from ui.main_window import MainWindow
# from services.vicon_connection import ViconConnection

def main():
    glutInit(sys.argv)
    app = QApplication(sys.argv)

    # vicon = ViconConnection('192.168.10.1', 'mug')
    main_window = MainWindow()
    main_window.show()

    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
