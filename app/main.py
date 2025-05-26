import sys
import numpy as np
from PyQt5.QtWidgets import QDockWidget,QSplitter, QVBoxLayout, QPushButton, QMainWindow, QWidget,QScrollArea, QOpenGLWidget, QApplication, QFormLayout,QComboBox,QGroupBox,QLineEdit,QLabel
from PyQt5.QtCore import QTimer, Qt
from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
import pygame

from main_window import MainWindow
from vicon_connection import ViconConnection



def main():
    glutInit(sys.argv)  # Initialize GLUT before starting the QApplication
    app = QApplication(sys.argv)

    vicon = ViconConnection('192.168.10.1', 'mug') #getting stuck here
    main_window = MainWindow(vicon)

    main_window.show()

    sys.exit(app.exec_())

if __name__ == '__main__':
    main()