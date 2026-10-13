"""Edit a MAVLink link: network (UDP/TCP) or USB/serial, plus sharing it with QGroundControl.

``text()`` / ``setText()`` read and write the pymavlink connection string, so
this drops in where a plain address field used to be. ``forward_to()`` is the
"host:port" to relay to (empty when sharing is off).
"""
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLineEdit, QSpinBox,
                             QStackedWidget, QVBoxLayout, QWidget)

from models import mavlink_links
from models.mavlink_links import BAUD_PRESETS, KIND_LABELS, QGC_DEFAULT_FORWARD, LinkSpec
from ui import theme

QGC_PORT = 14550


class LinkEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None, allow_forwarding: bool = True):
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(8)
        self.kind_combo = QComboBox()
        for kind in mavlink_links.KINDS:
            self.kind_combo.addItem(KIND_LABELS[kind], kind)
        self.kind_combo.setToolTip("WiFi / SITL: network. Telemetry radio, ExpressLRS TX module or a "
                                   "flight controller's own USB: USB / serial.")
        self.kind_combo.currentIndexChanged.connect(self._on_kind_changed)
        form.addRow("Link:", self.kind_combo)
        column.addLayout(form)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_network_page())
        self.pages.addWidget(self._build_serial_page())
        column.addWidget(self.pages)

        self.share_check = QCheckBox("Share with QGroundControl")
        self.share_check.setToolTip("Relay this link to QGroundControl (both ways), so QGC can use the same "
                                    "vehicle while Drone Trainer is connected. Needed for USB/serial links, "
                                    "which only one program can open.")
        self.share_check.toggled.connect(self._on_share_toggled)
        self._auto_shared = False    # sharing was switched on for a serial link, not by the user
        self.share_edit = QLineEdit(QGC_DEFAULT_FORWARD)
        self.share_edit.setToolTip("Where QGroundControl listens (its UDP auto-connect port is 14550)")
        self.share_edit.editingFinished.connect(self._on_edited)
        share_row = QHBoxLayout()
        share_row.addWidget(self.share_check)
        share_row.addWidget(self.share_edit, 1)
        self.share_widget = QWidget()
        self.share_widget.setLayout(share_row)
        share_row.setContentsMargins(0, 0, 0, 0)
        self.share_widget.setVisible(allow_forwarding)
        column.addWidget(self.share_widget)

        self.hint = theme.label("", "hint", wrap=True)
        column.addWidget(self.hint)
        self._updating = False
        self.refresh_ports()
        self._on_kind_changed()

    # -- pages ----------------------------------------------------------------------

    def _build_network_page(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(8)
        self.host_edit = QLineEdit("0.0.0.0")
        self.host_edit.editingFinished.connect(self._on_edited)
        self.host_label_text = "Listen on:"
        form.addRow(self.host_label_text, self.host_edit)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(14540)
        self.port_spin.setKeyboardTracking(False)
        self.port_spin.valueChanged.connect(self._on_edited)
        form.addRow("Port:", self.port_spin)
        self._network_form = form
        return page

    def _build_serial_page(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(8)
        port_row = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setEditable(True)     # a device that isn't listed can still be typed in
        self.device_combo.setToolTip("COM port on Windows, /dev/ttyUSB… or /dev/ttyACM… on Linux")
        self.device_combo.currentIndexChanged.connect(self._on_device_picked)
        self.device_combo.lineEdit().editingFinished.connect(self._on_edited)
        port_row.addWidget(self.device_combo, 1)
        self.refresh_button = theme.tool_button("refresh-cw", "Look for serial ports again")
        self.refresh_button.setProperty("variant", "square")
        self.refresh_button.setFixedSize(30, 30)
        self.refresh_button.clicked.connect(self.refresh_ports)
        port_row.addWidget(self.refresh_button)
        form.addRow("Port:", port_row)
        self.baud_combo = QComboBox()
        self.baud_combo.setEditable(True)
        for baud, label in BAUD_PRESETS:
            self.baud_combo.addItem(label, baud)
        self.baud_combo.currentIndexChanged.connect(self._on_edited)
        self.baud_combo.lineEdit().editingFinished.connect(self._on_edited)
        form.addRow("Baud:", self.baud_combo)
        return page

    # -- serial ports ----------------------------------------------------------------

    @pyqtSlot()
    def refresh_ports(self):
        current = self.device_combo.currentText().strip() if self.device_combo.count() else ""
        self._updating = True
        try:
            self.device_combo.clear()
            self._ports = mavlink_links.list_serial_ports()
            for port in self._ports:
                self.device_combo.addItem(port.label, port.device)
            if current:
                self._set_device(current)
        finally:
            self._updating = False
        if not self._ports and not current:
            self.device_combo.setEditText("")
        self._update_hint()

    def _set_device(self, device):
        index = self.device_combo.findData(device)
        if index >= 0:
            self.device_combo.setCurrentIndex(index)
        else:
            self.device_combo.setEditText(device)

    def _device(self) -> str:
        index = self.device_combo.currentIndex()
        text = self.device_combo.currentText().strip()
        if index >= 0 and text == self.device_combo.itemText(index):
            return self.device_combo.itemData(index)
        return text.split(" — ")[0].strip()

    def _baud(self) -> int:
        index = self.baud_combo.currentIndex()
        text = self.baud_combo.currentText().strip()
        if index >= 0 and text == self.baud_combo.itemText(index):
            return int(self.baud_combo.itemData(index))
        try:
            return int(text.split()[0])
        except (ValueError, IndexError):
            return mavlink_links.DEFAULT_BAUD

    def _set_baud(self, baud: int):
        index = self.baud_combo.findData(int(baud))
        if index >= 0:
            self.baud_combo.setCurrentIndex(index)
        else:
            self.baud_combo.setEditText(str(baud))

    def _on_device_picked(self, index):
        if self._updating or index < 0 or index >= len(getattr(self, "_ports", [])):
            return
        self._updating = True
        self._set_baud(self._ports[index].suggested_baud)   # a first guess from what the device says it is
        self._updating = False
        self.device_combo.lineEdit().setCursorPosition(0)   # show the port name, not the end of the label
        self._on_edited()

    # -- value ------------------------------------------------------------------------

    def link(self) -> LinkSpec:
        kind = self.kind_combo.currentData()
        if kind == "serial":
            return LinkSpec("serial", device=self._device(), baud=self._baud())
        host = self.host_edit.text().strip() or ("0.0.0.0" if kind == "udp_listen" else "127.0.0.1")
        return LinkSpec(kind, host, self.port_spin.value())

    def text(self) -> str:
        """The pymavlink connection string."""
        return self.link().connection_string()

    def setText(self, connection_string: str):
        link = mavlink_links.parse_link(connection_string)
        self._updating = True
        try:
            self.kind_combo.setCurrentIndex(max(0, self.kind_combo.findData(link.kind)))
            if link.kind == "serial":
                self._set_device(link.device)
                self._set_baud(link.baud)
            else:
                self.host_edit.setText(link.host)
                self.port_spin.setValue(link.port)
        finally:
            self._updating = False
        self._on_kind_changed()

    def forward_to(self) -> str:
        return self.share_edit.text().strip() if self.share_check.isChecked() else ""

    def set_forward_to(self, endpoint: str):
        self._updating = True
        self._set_shared(bool(endpoint), auto=False)
        if endpoint:
            self.share_edit.setText(endpoint)
        self._updating = False
        self._update_hint()

    def problem(self) -> str:
        """Why this link can't be used as entered ('' if it can)."""
        link = self.link()
        if link.kind == "serial" and not link.device:
            return "Pick the serial port (plug the radio / cable in, then Refresh)."
        if self.share_check.isChecked():
            endpoint = mavlink_links.parse_endpoint(self.share_edit.text())
            if endpoint is None:
                return "Enter where QGroundControl listens as host:port, e.g. 127.0.0.1:14550."
            if link.kind == "udp_listen" and endpoint[1] == link.port and endpoint[0] in (
                    "127.0.0.1", "localhost", "0.0.0.0", link.host):
                return (f"Drone Trainer already listens on port {link.port}; QGroundControl needs a different "
                        "port. Use another port for the vehicle (e.g. 14540), or point QGC at another one.")
        return ""

    # -- behaviour -----------------------------------------------------------------------

    def _on_kind_changed(self, *_):
        kind = self.kind_combo.currentData()
        self.pages.setCurrentIndex(1 if kind == "serial" else 0)
        label = self._network_form.labelForField(self.host_edit)
        if label is not None:
            label.setText("Listen on:" if kind == "udp_listen" else "Host:")
        if not self._updating:
            if kind == "serial" and not self.share_check.isChecked():
                # A serial port is exclusive: QGroundControl can only use it through us.
                self._set_shared(True, auto=True)
            elif kind != "serial" and self._auto_shared:
                self._set_shared(False, auto=False)   # we turned it on for serial; the user didn't
        self._on_edited()

    def _set_shared(self, shared: bool, auto: bool):
        self.share_check.blockSignals(True)
        self.share_check.setChecked(shared)
        self.share_check.blockSignals(False)
        self._auto_shared = auto and shared

    def _on_share_toggled(self, _checked):
        self._auto_shared = False   # the user decided
        self._on_edited()

    def _on_edited(self, *_):
        if self._updating:
            return
        self._update_hint()
        self.changed.emit()

    def _update_hint(self):
        link = self.link()
        problem = self.problem()
        if problem:
            text = problem
            theme.set_tone(self.hint, "danger")
        else:
            theme.set_tone(self.hint, None)
            if link.kind == "serial":
                text = ("Only one program can open a serial port; with sharing on, QGroundControl gets the "
                        "vehicle through Drone Trainer (leave QGC's own serial auto-connect off).")
            elif link.kind == "udp_listen" and link.port == QGC_PORT:
                text = ("QGroundControl also listens on UDP 14550. If it's open too, only one of them gets the "
                        "vehicle's packets: use another port here (PX4 SITL sends to 14540 for this), or share "
                        "with QGC on a different port.")
            elif self.share_check.isChecked():
                text = "QGroundControl sees this vehicle through Drone Trainer while it's connected."
            else:
                text = ""
        self.hint.setText(text)
        self.hint.setVisible(bool(text))
