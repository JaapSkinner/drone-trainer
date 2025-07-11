import functools
import traceback
from abc import ABCMeta, abstractmethod
from enum import Enum, auto
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

class ServiceLevel(Enum):
    STOPPED = auto()
    RUNNING = auto()
    WARNING = auto()
    ERROR = auto()
    
class DebugLevel(Enum):
    PASS = 0
    LOG = 1
    STOP = 2
    HALT = 3

# Combine QObject's metaclass and ABCMeta
class MetaService(type(QObject), ABCMeta):
    pass

class ServiceBase(QObject, metaclass=MetaService):  
    status_changed = pyqtSignal(int, str)  # emit both enum and label
    error_occurred = pyqtSignal(str)

    def __init__(self, debug_level=DebugLevel.LOG):
        super().__init__()
        if isinstance(debug_level, DebugLevel):
            self._debug_level = debug_level
        else:
            raise ValueError("debug_level must be a DebugLevel enum value")
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self._on_start)
        self._thread.finished.connect(self._on_stop)
        
        self._status_level = ServiceLevel.STOPPED
        self._status_label = ""


        # Bind error signal to handler
        self.error_occurred.connect(self._handle_error)

    @property
    def status(self):
        return self._status_level

    @property
    def debug_level(self):
        return self._debug_level
    
    @status.setter
    def status(self, level):
        self._status_level = level
        self._emit_status_change()

    def set_status(self, level: ServiceLevel, label: str = ""):
        self._status_level = level
        self._status_label = label
        self._emit_status_change()
        
    @debug_level.setter
    def debug_level(self, level):
        if isinstance(level, DebugLevel):
            self._debug_level = level
        else:
            raise ValueError("debug_level must be a DebugLevel enum value")

    def _emit_status_change(self):
        self.status_changed.emit(self._status_level.value, self._status_label)
    
    def start(self):
        if not self._thread.isRunning():
            self._thread.start()

    def stop(self):
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()

    @pyqtSlot()
    def _on_start(self):
        self.status = ServiceLevel.RUNNING
        self.on_start()

    @pyqtSlot()
    def _on_stop(self):
        self.status = ServiceLevel.STOPPED
        self.on_stop()

    @abstractmethod
    def on_start(self):
        """Override: Initialization in thread context."""
        pass

    @abstractmethod
    def on_stop(self):
        """Override: Cleanup in thread context."""
        pass

    @abstractmethod
    def update(self):
        """Override: Periodic or event-driven update logic."""
        pass

    def safe(self, func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self.error_occurred.emit(f"{e}\n{traceback.format_exc()}")
        return wrapper

    @pyqtSlot(str)
    def _handle_error(self, error_str):
        print(f"[{self.__class__.__name__}] Error:\n{error_str}")
        if self._debug_level == DebugLevel.PASS:
            # ignore error, continue
            return
        elif self._debug_level == DebugLevel.LOG:
            # log only, continue running
            return
        elif self._debug_level == DebugLevel.STOP:
            # log and stop service thread
            self.status = ServiceLevel.ERROR
            self.stop()
        elif self._debug_level == DebugLevel.HALT:
            # log, stop service thread and exit entire program
            self.status = ServiceLevel.ERROR
            self.stop()
            import sys
            sys.exit(1)
