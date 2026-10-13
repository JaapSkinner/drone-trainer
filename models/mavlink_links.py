"""MAVLink link addresses: build, read and describe them, and find serial (USB) ports.

A connection is stored as a pymavlink connection string
(``mavutil.mavlink_connection``):

* ``udpin:0.0.0.0:14540``  listen for a vehicle on a UDP port (WiFi, SITL)
* ``udpout:10.0.0.1:14550`` send to a vehicle that waits for us
* ``tcp:127.0.0.1:5760``   TCP client (e.g. some SITLs)
* ``COM3,460800`` / ``/dev/ttyUSB0,57600``  serial port, baud after the comma
  (pymavlink's ``mavserial`` splits it off)

Serial baud rates that matter in practice:

* 57600 — SiK / 3DR / Holybro telemetry radios (their default)
* 115200 — the usual default; a Pixhawk on its own USB port ignores the baud
* 460800 — ExpressLRS in MAVLink mode, over the TX module's USB (fixed by ELRS)
* 921600 — high-speed telemetry links

Only one program can open a serial port. To use QGroundControl at the same
time, let Drone Trainer forward the link to QGC (see ``forward_to`` on the
connection config).
"""
from dataclasses import dataclass
from typing import List, Optional

KINDS = ("udp_listen", "udp_send", "tcp", "serial")
KIND_LABELS = {
    "udp_listen": "Network (UDP, listen)",
    "udp_send": "Network (UDP, send to)",
    "tcp": "Network (TCP)",
    "serial": "USB / serial",
}
BAUD_PRESETS = (
    (57600, "57600 — telemetry radio (SiK)"),
    (115200, "115200 — default / Pixhawk USB"),
    (460800, "460800 — ExpressLRS MAVLink"),
    (921600, "921600 — high-speed link"),
)
DEFAULT_BAUD = 115200
QGC_DEFAULT_FORWARD = "127.0.0.1:14550"   # QGroundControl's UDP auto-connect port


@dataclass
class LinkSpec:
    kind: str = "udp_listen"
    host: str = "0.0.0.0"
    port: int = 14540
    device: str = ""
    baud: int = DEFAULT_BAUD

    def connection_string(self) -> str:
        if self.kind == "serial":
            return f"{self.device},{int(self.baud)}"
        prefix = {"udp_listen": "udpin", "udp_send": "udpout", "tcp": "tcp"}[self.kind]
        return f"{prefix}:{self.host}:{int(self.port)}"

    def describe(self) -> str:
        if self.kind == "serial":
            return f"{self.device} at {int(self.baud)} baud"
        if self.kind == "udp_listen":
            return f"listening on UDP port {self.port}"
        if self.kind == "udp_send":
            return f"UDP to {self.host}:{self.port}"
        return f"TCP {self.host}:{self.port}"


def parse_link(connection_string: str) -> LinkSpec:
    """Read a stored connection string back into its parts (unknown forms come back as UDP)."""
    text = (connection_string or "").strip()
    for prefix, kind in (("udpin:", "udp_listen"), ("udpout:", "udp_send"), ("udp:", "udp_listen"),
                         ("tcp:", "tcp")):
        if text.startswith(prefix):
            host, _, port = text[len(prefix):].rpartition(":")
            try:
                return LinkSpec(kind, host or "0.0.0.0", int(port))
            except ValueError:
                return LinkSpec(kind, host or "0.0.0.0")
    device, _, baud = text.partition(",")
    if device and ":" not in device:      # COM3, \\.\COM10, /dev/ttyUSB0 … (no "proto:")
        try:
            return LinkSpec("serial", device=device, baud=int(baud) if baud else DEFAULT_BAUD)
        except ValueError:
            return LinkSpec("serial", device=device)
    return LinkSpec()


def is_serial(connection_string: str) -> bool:
    return parse_link(connection_string).kind == "serial"


@dataclass
class SerialPortInfo:
    device: str             # COM3, /dev/ttyACM0 …
    description: str        # what the OS calls it
    suggested_baud: int

    @property
    def label(self) -> str:
        if self.description and self.description != self.device and self.description != "n/a":
            return f"{self.device} — {self.description}"
        return self.device


def suggest_baud(description: str = "", manufacturer: str = "", vid: Optional[int] = None) -> int:
    """A first guess at the baud rate from what the USB device says it is."""
    text = f"{description} {manufacturer}".lower()
    if any(k in text for k in ("px4", "pixhawk", "ardupilot", "cube", "fmu", "holybro durandal")):
        return DEFAULT_BAUD          # flight controller's own USB: the baud is ignored
    if "expresslrs" in text or "elrs" in text:
        return 460800
    if vid == 0x0403 or "ftdi" in text or "sik" in text or "3dr" in text or "radio" in text:
        return 57600                 # FTDI-based SiK/3DR telemetry radios
    return DEFAULT_BAUD


def list_serial_ports() -> List[SerialPortInfo]:
    """Serial ports on this PC (empty if pyserial isn't installed)."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    ports = []
    for port in sorted(list_ports.comports(), key=lambda p: p.device):
        description = (port.description or "").strip()
        ports.append(SerialPortInfo(port.device, description,
                                    suggest_baud(description, port.manufacturer or "", port.vid)))
    return ports


def parse_endpoint(text: str, default_port: int = 14550):
    """'host:port' → (host, port), or None if it can't be read."""
    host, _, port = (text or "").strip().rpartition(":")
    if not host:
        host, port = (text or "").strip(), str(default_port)
    try:
        port = int(port)
    except ValueError:
        return None
    if not host or not (0 < port < 65536):
        return None
    return host, port
