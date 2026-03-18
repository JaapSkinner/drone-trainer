import functools
import logging
import traceback
import threading
from abc import ABCMeta, abstractmethod
from enum import Enum, auto
from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication

logger = logging.getLogger(__name__)

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
        self._signals_connected = False
        # A QObject instance that will live in the service's QThread and can
        # be used as the parent for QTimers and other thread-affine QObjects.
        self._thread_parent = QObject()

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
        logger.debug("Starting service %s (QThread.running=%s) python_thread=%s", self.__class__.__name__, getattr(self._thread, 'isRunning', lambda: False)(), threading.get_ident())
        if self._thread.isRunning():
            return

        # Ensure moveToThread and starting the QThread happen from the
        # object's current thread. If start() is called from another
        # thread, schedule the helper to run in the object's thread.
        current = QThread.currentThread()
        try:
            obj_thread = self.thread()
        except Exception:
            obj_thread = None

        logger.debug("start(): current_qthread=%s obj_thread=%s python_thread=%s", current, obj_thread, threading.get_ident())

        if obj_thread is current:
            # We're in the object's thread already — perform the start immediately
            self._do_start_thread()
        else:
            # Schedule the operation to run on the object's thread to ensure
            # moveToThread is invoked from the correct thread.
            from PyQt5.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(self, "_do_start_thread", Qt.QueuedConnection)

    def stop(self):
        logger.debug("Stopping service %s (QThread.running=%s) python_thread=%s", self.__class__.__name__, getattr(self._thread, 'isRunning', lambda: False)(), threading.get_ident())

        try:
            if self._thread is not None and self._thread.isRunning():
                logger.debug("Calling quit() on thread for service %s", self.__class__.__name__)
                self._thread.quit()
                # Wait up to 2 seconds for a clean shutdown
                if not self._thread.wait(2000):
                    # As a last resort, terminate the thread to avoid crashes
                    try:
                        self._thread.terminate()
                    except Exception:
                        pass
                    self._thread.wait()
        except Exception:
            pass

        # We intentionally avoid calling moveToThread here because calling
        # moveToThread from the wrong thread causes Qt warnings. We already
        # stop and delete the QThread above which prevents the 'destroyed
        # while running' crash — moving the QObject back to main thread
        # is unnecessary and was the source of recent warnings.
        try:
            app = QApplication.instance()
            if app is not None and self.thread() is not None:
                logger.debug("Service %s currently on thread %s; not moving to main thread to avoid cross-thread warnings", self.__class__.__name__, self.thread())
        except Exception:
            pass

        # Schedule thread object for deletion (no-op if already deleted)
        try:
            if hasattr(self, '_thread') and self._thread is not None:
                self._thread.deleteLater()
        except Exception:
            pass
        finally:
            self._thread = None

    def __del__(self):
        # Best-effort cleanup if stop() wasn't called explicitly.
        try:
            self.stop()
        except Exception:
            pass

    @pyqtSlot()
    def _on_start(self):
        self.status = ServiceLevel.RUNNING
        self.on_start()

    @pyqtSlot()
    def _do_start_thread(self):
        """Helper that runs in the object's current thread to safely call
        moveToThread and start the QThread. This avoids moveToThread being
        called from the wrong thread."""
        logger.debug("_do_start_thread for %s: current python thread=%s, current_qthread=%s, target_qthread=%s", self.__class__.__name__, threading.get_ident(), QThread.currentThread(), self._thread)
        try:
            if not self._signals_connected:
                try:
                    self.moveToThread(self._thread)
                except Exception:
                    logger.exception("moveToThread failed in _do_start_thread for %s", self.__class__.__name__)
                try:
                    self._thread.started.connect(self._on_start)
                    self._thread.finished.connect(self._on_stop)
                    self._signals_connected = True
                except Exception:
                    logger.exception("Failed to connect thread signals for %s", self.__class__.__name__)

            if not self._thread.isRunning():
                self._thread.start()
                # Move the helper parent into the new QThread so services can
                # parent timers to an object that lives in the service thread.
                try:
                    self._thread_parent.moveToThread(self._thread)
                except Exception:
                    logger.exception("Failed to move thread parent for %s", self.__class__.__name__)
                logger.debug("QThread started for service %s", self.__class__.__name__)
        except Exception:
            logger.exception("Error during _do_start_thread for %s", self.__class__.__name__)

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
        logger.error(f"[{self.__class__.__name__}] Error:\n{error_str}")
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

    def get_thread_parent(self) -> QObject:
        """Return a QObject instance that lives in the service QThread once started.

        Use this object as the parent for QTimers and other QObject parents that
        need to live in the service thread (prevents cross-thread start/stop).
        """
        return getattr(self, '_thread_parent', None)
