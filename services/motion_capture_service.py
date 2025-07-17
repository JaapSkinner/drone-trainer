from services.service_base import ServiceBase, ServiceLevel
from PyQt5.QtCore import pyqtSlot, pyqtSignal
from dataclasses import dataclass

@dataclass
class OptiTrackConfig:
    server_ip: str = '127.0.0.1'
    client_ip: str = '127.0.0.1'
    multicast: bool = False
    rigid_body_ids: list = None  # List of IDs to track, or None for all
    # Add more fields as needed

class MotionCaptureService(ServiceBase):
    mocap_updated = pyqtSignal(object)

    def __init__(self, config: OptiTrackConfig = None, debug_level=None):
        super().__init__(debug_level=debug_level)
        self.config = config or OptiTrackConfig()
        self.connection = None
        self._last_status = None
        self._last_status_label = None

    def set_config(self, config: OptiTrackConfig):
        self.config = config
        self.status_label = "OptiTrack config updated"
        self.status = ServiceLevel.STOPPED

    def try_create_connection(self):
        # Import here to avoid circular import if needed
        from services.optitrack.NatNetClient import NatNetClient
        if self.connection:
            self.stop()
        try:
            self.connection = NatNetClient(
                server_ip=self.config.server_ip,
                client_ip=self.config.client_ip,
                use_multicast=self.config.multicast
            )
            # Setup listeners/callbacks here as needed
            self.connection.rigid_body_listener = self._on_rigid_body_update
            self.status_label = "OptiTrack connection created"
            self.status = ServiceLevel.RUNNING
            return True
        except Exception as e:
            self.connection = None
            self.status_label = f"OptiTrack connection failed: {e}"
            self.status = ServiceLevel.ERROR
            return False

    def _on_start(self):
        self.start()

    def _on_stop(self):
        self.stop()

    def start(self):
        if not self.connection:
            if not self.try_create_connection():
                return
        try:
            self.connection.run()  # This starts the NatNet client loop
            self.status_label = "OptiTrack tracking started"
            self.status = ServiceLevel.RUNNING
        except Exception as e:
            self.status_label = f"Failed to start tracking: {e}"
            self.status = ServiceLevel.ERROR

    def stop(self):
        if self.connection:
            try:
                self.connection.shutdown()
            except Exception:
                pass
            self.connection = None
            self.status_label = "OptiTrack tracking stopped"
            self.status = ServiceLevel.STOPPED

    def update(self):
        # Periodically check connection status and publish
        if self.connection:
            # Example: check if still running, update status if needed
            is_connected = getattr(self.connection, 'is_connected', lambda: True)()
            if not is_connected:
                self.status_label = "OptiTrack disconnected"
                self.status = ServiceLevel.ERROR
            else:
                self.status_label = "OptiTrack running"
                self.status = ServiceLevel.RUNNING
        else:
            self.status_label = "OptiTrack not connected"
            self.status = ServiceLevel.STOPPED

    @pyqtSlot(object)
    def configure(self, config):
        self.set_config(config)

    @pyqtSlot()
    def start_service(self):
        self.start()

    @pyqtSlot()
    def stop_service(self):
        self.stop()

    def _on_rigid_body_update(self, frame, rigid_body):
        # You can filter by self.config.rigid_body_ids if needed
        self.mocap_updated.emit(rigid_body)
