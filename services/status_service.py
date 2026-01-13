"""
Status Service for monitoring and reporting service health.

This service periodically polls all registered services and updates
the status panel with their current state and health metrics.
"""
from PyQt5.QtCore import pyqtSignal, QTimer
from services.service_base import ServiceBase, DebugLevel, ServiceLevel
from time import time


class StatusService(ServiceBase):
    """Service for monitoring and reporting the health of other services.
    
    Periodically polls input service, mavlink service, and other registered
    services to update the status panel with their current state.
    
    Attributes:
        status_panel: UI panel for displaying status information
        input_service: Input service to monitor
        mavlink_service: MAVLink service to monitor
    """
    
    def __init__(self, status_panel, input_service, mavlink_service=None, debug_level=DebugLevel.LOG):
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
        self.timer = None

    def on_start(self):
        """Start the status monitoring timer."""
        self.timer = QTimer()
        self.timer.setInterval(1000)  # 1 Hz
        self.timer.timeout.connect(self.safe(self.update))
        self.timer.start()

    def on_stop(self):
        """Stop the status monitoring timer."""
        if self.timer:
            self.timer.stop()
            self.timer.deleteLater()
            self.timer = None

    def update(self):
        """Update status panel with current service states."""
        # Input Device status
        if self.input_service is not None:
            input_svc = self.input_service
            self.status_panel.handle_status_change(
                input_svc.status.value, 
                getattr(input_svc, "status_label", ""), 
                "input"
            )
        
        # MAVLink service status
        if self.mavlink_service is not None:
            mavlink_svc = self.mavlink_service
            rate_hz, active_conns = mavlink_svc.get_health_metrics()
            
            # Build status label with rate and connection info
            if active_conns > 0:
                label = f"{active_conns} drones @ {rate_hz:.0f} Hz"
            else:
                label = getattr(mavlink_svc, "_status_label", "Not Connected")
            
            self.status_panel.handle_status_change(
                mavlink_svc.status.value,
                label,
                "mavlink"
            )
    
    def set_mavlink_service(self, mavlink_service):
        """Set or update the mavlink service reference.
        
        Args:
            mavlink_service: MAVLink service to monitor
        """
        self.mavlink_service = mavlink_service
