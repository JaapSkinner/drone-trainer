from PyQt5.QtCore import QTimer, Qt, pyqtSlot
from PyQt5.QtWidgets import QMainWindow, QSplitter,QHBoxLayout, QWidget, QApplication
from PyQt5.QtGui import QFontDatabase, QFont

from services.input_service import InputService, InputType
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

        # Initialize input service with default settings
        self.input_service = InputService(
            self.glWidget,
            input_type=InputType.CONTROLLER,
            sensitivity=1.0
        )
        self.object_service.load_input_service(self.input_service)
        
        # Connect GL widget to input service for keyboard events
        self.glWidget.set_input_service(self.input_service)

        self.status_service = StatusService(
            self.status_panel,
            self.input_service,
            None  # Placeholder for mavlink service
        )
        self.status_service.start()
        
        
        self.input_service.input_updated.connect(self.on_input_update)
        self.input_service.start()
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
        self.config_panel = self.dock.panels[0]  # Config panel is first
        
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
        
        # Connect config panel signals to input service
        self.config_panel.input_type_changed.connect(self.on_input_type_changed)
        self.config_panel.sensitivity_changed.connect(self.on_sensitivity_changed)
        
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
    def on_input_update(self, obj):
        """Handle input device updates (replaces on_joystick_update)"""
        self.object_panel.refresh()
        self.glWidget.update()
    
    @pyqtSlot(object)
    def on_input_type_changed(self, input_type):
        """Handle input type change from config panel"""
        if hasattr(self, 'input_service'):
            self.input_service.set_input_type(input_type)
    
    @pyqtSlot(float)
    def on_sensitivity_changed(self, sensitivity):
        """Handle sensitivity change from config panel"""
        if hasattr(self, 'input_service'):
            self.input_service.set_sensitivity(sensitivity)

        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.overlay.setGeometry(self.rect())
        self.status_panel.move(self.width() - self.status_panel.width() - 20, 20)

    def closeEvent(self, event):
        """Properly stop all services before closing the application."""
        # Stop services to ensure timers are stopped in their own threads
        if hasattr(self, 'status_service'):
            self.status_service.stop()
        if hasattr(self, 'input_service'):
            self.input_service.stop()
        
        # Stop the GL widget timer
        if hasattr(self, 'glWidget') and self.glWidget and hasattr(self.glWidget, 'timer'):
            self.glWidget.timer.stop()
        
        # Accept the close event
        super().closeEvent(event)
        event.accept()