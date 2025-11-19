from PyQt5.QtCore import QTimer, Qt, pyqtSlot
from PyQt5.QtWidgets import QMainWindow, QSplitter,QHBoxLayout, QWidget, QApplication
from PyQt5.QtGui import QFontDatabase, QFont

from services.joystick_service import JoystickService
from services.object_service import ObjectService
from services.status_service import StatusService

from ui.gl_widget.gl_widget import GLWidget
from ui.dock.dock_manager import DockManager
from models.structs import PositionData
from ui.navbar.navbar import SideNavbar
from ui.style import load_stylesheet
from ui.status_panel.status_panel import StatusPanel


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Load and set global font
        font_id = QFontDatabase.addApplicationFont('ui/assets/fonts/NotoSan.ttf')
        if font_id != -1:
            family = QFontDatabase.applicationFontFamilies(font_id)[0]
            QFontDatabase.addApplicationFont('ui/assets/fonts/NotoSan.ttf')
            self.setFont(QFont(family, 11))
            QApplication.setFont(QFont(family, 11))


        # self.vicon = vicon

        self.object_service = ObjectService(None, debug_level=None)  # Use default debug level

        self.glWidget = None
        self.initUI()

        self.joystick_service = JoystickService(self.glWidget)
        self.object_service.load_input_service(self.joystick_service)


        self.status_service = StatusService(
            self.status_panel,
            self.joystick_service,
            None  # Placeholder for mavlink service
        )
        self.status_service.start()
        
        
        self.joystick_service.joystick_updated.connect(self.on_joystick_update)
        self.joystick_service.start()
        # self.vicon.position_updated.connect(self.update_vicon_position)
        

        
        self.setStyleSheet(load_stylesheet('ui/main_window.qss'))


    def initUI(self):
        self.setWindowTitle('Collaborative Control Interface')
        self.setGeometry(50, 50, 1200, 800)

        # Top-level horizontal layout
        central_widget = QWidget(self)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central_widget)

        # NavBar on far left
        self.navbar = SideNavbar()
        main_layout.addWidget(self.navbar)

        # Dock and GLWidget on the right
        self.glWidget = GLWidget(object_service=self.object_service)
        self.dock = DockManager(self.glWidget, self, self.object_service)
        self.object_panel = self.dock.panels[4]
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.dock)
        splitter.addWidget(self.glWidget)
        splitter.setStretchFactor(1, 1)  # let GLWidget expand
        main_layout.addWidget(splitter)
        splitter.setCollapsible(0, False)  # Prevent dock collapsing
        splitter.setCollapsible(1, False)  # Prevent GL collapsing
        self.glWidget.setMinimumWidth(200)
        self.dock.setMinimumWidth(250)
        
        self.navbar.panel_selected.connect(self.dock.set_active_panel)
        
        # === Overlay container ===
        self.overlay = QWidget(central_widget)
        self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.overlay.setStyleSheet("background: transparent;")
        self.overlay.setGeometry(self.rect())
        self.overlay.raise_()

        # === Status panel inside overlay ===
        self.status_panel = StatusPanel(self.overlay)
        self.status_panel.move(self.width() - self.status_panel.width() - 20, 20)
        self.status_panel.show()



    @pyqtSlot(PositionData)
    def update_vicon_position(self, pos_data: PositionData):
        for obj in self.glWidget.objects:
            if obj.tracked and obj.name == pos_data.name:
                obj.x_pos = pos_data.x
                obj.y_pos = pos_data.y
                obj.z_pos = pos_data.z
                obj.x_rot = pos_data.x_rot
                obj.y_rot = pos_data.y_rot
                obj.z_rot = pos_data.z_rot
        self.object_panel.refresh()

    @pyqtSlot(object)
    def on_joystick_update(self, obj):
        self.object_panel.refresh()
        self.glWidget.update()

        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.overlay.setGeometry(self.rect())
        self.status_panel.move(self.width() - self.status_panel.width() - 20, 20)