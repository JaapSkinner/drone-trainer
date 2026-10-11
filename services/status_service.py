"""
Status Service for monitoring and reporting service health.

This service periodically polls all registered services and updates
the status panel with their current state and health metrics.
"""
from PyQt5.QtCore import pyqtSignal, QTimer
import logging
from services.service_base import ServiceBase, DebugLevel, ServiceLevel
from time import time


logger = logging.getLogger(__name__)


class StatusService(ServiceBase):
    """Service for monitoring and reporting the health of other services.

    Periodically polls input service, mavlink service, and other registered
    services to update the status panel with their current state.

    Updates reach the panel through ``status_update`` so the widget is only
    touched on the GUI thread (this service polls from its own thread).

    Attributes:
        status_panel: UI panel for displaying status information
        input_service: Input service to monitor
        mavlink_service: MAVLink service to monitor
    """

    status_update = pyqtSignal(int, str, str)  # level, label, target

    def __init__(self, status_panel, input_service, mavlink_service=None, debug_level=DebugLevel.LOG,
                 motion_capture_service=None):
        """Initialize the status service.
        
        Args:
            status_panel: UI panel for displaying status
            input_service: Input service to monitor
            mavlink_service: MAVLink service to monitor (optional)
            debug_level: Debug level for error handling
        """
        super().__init__(debug_level)
        self.status_panel = status_panel
        self.input_service = input_service
        self.mavlink_service = mavlink_service
        self.motion_capture_service = motion_capture_service
        self.timer = None
        if status_panel is not None:
            self.status_update.connect(status_panel.handle_status_change)

    def on_start(self):
        """Start the status monitoring timer."""
        parent = getattr(self, 'get_thread_parent', lambda: None)()
        if parent is None:
            parent = self
        logger.info("StatusService.on_start() parent=%s", parent)
        self.timer = QTimer(parent)
        self.timer.setInterval(1000)  # 1 Hz
        self.timer.timeout.connect(self.safe(self.update))
        self.timer.start()

    def on_stop(self):
        """Stop the status monitoring timer."""
        logger.info("StatusService.on_stop()")
        if self.timer:
            self.timer.stop()
            self.timer.deleteLater()
            self.timer = None

    def update(self):
        """Update status panel with current service states."""
        if self.motion_capture_service is not None:
            mocap = self.motion_capture_service
            self.status_update.emit(mocap.status.value, mocap.status_text, "motion_capture")

        # Input Device status
        if self.input_service is not None:
            input_svc = self.input_service
            self.status_update.emit(
                input_svc.status.value, 
                getattr(input_svc, "status_label", ""), 
                "input"
            )
        
        # MAVLink service status - only show when there are connections or mavlink-enabled objects
        if self.mavlink_service is not None:
            mavlink_svc = self.mavlink_service
            rate_hz, active_conns = mavlink_svc.get_health_metrics()
            mavlink_objects = mavlink_svc.get_mavlink_objects()
            
            # Count enabled mavlink objects
            enabled_objects = sum(1 for cfg in mavlink_objects.values() if cfg.enabled)
            
            # Only show mavlink status if there are connections or enabled objects
            if active_conns > 0:
                # Show connection count and health
                if active_conns == 1:
                    # For single connection, show health details
                    label = f"1 drone @ {rate_hz:.0f} Hz"
                else:
                    label = f"{active_conns} drones @ {rate_hz:.0f} Hz"
                self.status_update.emit(
                    mavlink_svc.status.value,
                    label,
                    "mavlink"
                )
            elif enabled_objects > 0:
                # Objects configured but not connected
                label = f"Not Connected ({enabled_objects} objects configured)"
                self.status_update.emit(
                    ServiceLevel.WARNING.value,
                    label,
                    "mavlink"
                )
            else:
                # No connections or objects - hide mavlink status
                self.status_update.emit(
                    ServiceLevel.STOPPED.value,
                    "",
                    "mavlink"
                )
    
    def set_mavlink_service(self, mavlink_service):
        """Set or update the mavlink service reference.
        
        Args:
            mavlink_service: MAVLink service to monitor
        """
        self.mavlink_service = mavlink_service
