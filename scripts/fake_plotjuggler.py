"""A stand-in for PlotJuggler's UDP Server / WebSocket Server (JSON) to check live plotting.

    python scripts/fake_plotjuggler.py              # UDP on 9870 and WebSocket on 9871
    python scripts/fake_plotjuggler.py --udp 9870 --websocket 0

Every couple of seconds it prints the message rate and the series PlotJuggler
would create. :func:`flatten` follows PlotJuggler's JSON parser
(``plotjuggler_app/nlohmann_parsers.cpp``): object keys join with ``/``,
array items become ``name[i]``, booleans are 0/1 and strings are skipped.
"""
import argparse
import json
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def flatten(value, prefix=""):
    """{series name: number} the way PlotJuggler's JSON parser names them."""
    out = {}
    if isinstance(value, list):
        if prefix == "":   # a top-level array is a batch of messages (PlotJuggler ≥ 3.16)
            for element in value:
                out.update(flatten(element))
            return out
        for i, element in enumerate(value):
            out.update(flatten(element, f"{prefix}[{i}]"))
    elif isinstance(value, dict):
        for key, element in value.items():
            out.update(flatten(element, f"{prefix}/{key}"))
    elif isinstance(value, bool):
        out[prefix] = float(value)
    elif isinstance(value, (int, float)):
        out[prefix] = float(value)
    return out


class Collector:
    def __init__(self):
        self.messages = 0
        self.series = {}
        self.errors = 0

    def feed(self, raw: bytes):
        try:
            self.series.update(flatten(json.loads(raw)))
            self.messages += 1
        except ValueError as exc:   # PlotJuggler would stop the stream on this
            self.errors += 1
            print(f"bad message ({exc}): {raw[:120]!r}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--udp", type=int, default=9870, help="UDP port (0 = off)")
    parser.add_argument("--websocket", type=int, default=9871, help="WebSocket port (0 = off)")
    parser.add_argument("--duration", type=float, default=0.0, help="seconds to run (0 = forever)")
    parser.add_argument("--report", type=float, default=2.0, help="seconds between reports")
    args = parser.parse_args()

    from PyQt5.QtCore import QCoreApplication, QTimer
    from PyQt5.QtNetwork import QHostAddress
    from PyQt5.QtWebSockets import QWebSocketServer

    app = QCoreApplication([sys.argv[0]])
    collector = Collector()

    if args.udp:
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind(("0.0.0.0", args.udp))
        udp.setblocking(False)

        def read_udp():
            while True:
                try:
                    data, _ = udp.recvfrom(65535)
                except BlockingIOError:
                    return
                collector.feed(data)
        poll = QTimer()
        poll.timeout.connect(read_udp)
        poll.start(5)
        print(f"UDP Server (JSON) listening on port {args.udp}", flush=True)

    if args.websocket:
        server = QWebSocketServer("fake PlotJuggler", QWebSocketServer.NonSecureMode)
        clients = []

        def on_connection():
            client = server.nextPendingConnection()
            client.textMessageReceived.connect(lambda text: collector.feed(text.encode("utf-8")))
            clients.append(client)
            print("WebSocket client connected", flush=True)
        server.newConnection.connect(on_connection)
        if not server.listen(QHostAddress.Any, args.websocket):
            print(f"Can't listen on WebSocket port {args.websocket}: {server.errorString()}", flush=True)
            return 1
        print(f"WebSocket Server (JSON) listening on port {args.websocket}", flush=True)

    last = {"t": time.monotonic(), "n": 0}

    def report():
        now = time.monotonic()
        rate = (collector.messages - last["n"]) / (now - last["t"])
        last.update(t=now, n=collector.messages)
        names = sorted(collector.series)
        print(f"{rate:5.1f} msg/s, {len(names)} series", flush=True)
        for name in names[:40]:
            print(f"   {name} = {collector.series[name]:.3f}", flush=True)
        if len(names) > 40:
            print(f"   … and {len(names) - 40} more", flush=True)
    timer = QTimer()
    timer.timeout.connect(report)
    timer.start(int(args.report * 1000))
    if args.duration:
        QTimer.singleShot(int(args.duration * 1000), app.quit)
    app.exec_()
    return 1 if collector.errors else 0


if __name__ == "__main__":
    sys.exit(main())
