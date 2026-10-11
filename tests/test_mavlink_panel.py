import unittest
from unittest import mock

from qt_test_utils import get_app, wait_until

from services import mavlink_service
from services.mavlink_service import MavlinkService
from services.object_service import ObjectService
from test_mavlink_service import _fake_connect
from ui.dock.panels.mavlink_panel import MavlinkPanel


class MavlinkPanelConnectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def make_panel(self, **fake):
        patch = mock.patch.object(mavlink_service.MavlinkConnection, "connect", _fake_connect(**fake))
        patch.start()
        self.addCleanup(patch.stop)
        self.service = MavlinkService()
        panel = MavlinkPanel(mavlink_service=self.service, object_service=ObjectService())
        panel.set_mavlink_service(self.service)
        self.addCleanup(panel.deleteLater)
        return panel

    def test_connect_runs_in_the_background(self):
        panel = self.make_panel(heartbeat_system_id=2)
        panel.connection_input.setText("udpin:0.0.0.0:14550")
        panel.name_input.setText("Quad")
        panel.connect_btn.click()
        self.assertEqual(panel.connect_btn.text(), "Connecting…")   # returned immediately
        self.assertTrue(wait_until(lambda: panel.connect_btn.isEnabled(), timeout_s=3.0))
        self.assertIn("Quad", panel._connection_cards)
        self.assertIn("Connected", panel._connection_cards["Quad"].status_label.text())

    def test_failed_connect_shows_the_reason(self):
        panel = self.make_panel(succeed=False)
        panel.connection_input.setText("udpin:0.0.0.0:14551")
        with mock.patch("ui.dock.panels.mavlink_panel.QMessageBox.warning") as warning:
            panel.connect_btn.click()
            self.assertTrue(wait_until(lambda: warning.called, timeout_s=3.0))
        self.assertIn("No heartbeat", warning.call_args[0][2])


if __name__ == "__main__":
    unittest.main()
