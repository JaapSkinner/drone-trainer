"""Checks on local modifications to the vendored NatNet SDK client."""
import socket
import sys
import unittest

from services.motion_capture.natnet.NatNetClient import NatNetClient


def _free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class NatNetMulticastTests(unittest.TestCase):
    def test_multicast_data_socket_receives_frames(self):
        client = NatNetClient()
        client.set_client_address("127.0.0.1")
        client.set_use_multicast(True)
        client.data_port = _free_udp_port()
        try:
            data_socket = client._NatNetClient__create_data_socket()
        except OSError as exc:  # no multicast support in this environment
            self.skipTest(f"multicast unavailable: {exc}")
        data_socket.settimeout(1.0)

        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sender.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton("127.0.0.1"))
        sender.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        try:
            sender.sendto(b"frame", (client.multicast_address, client.data_port))
            data, _ = data_socket.recvfrom(64)
        except socket.timeout:
            self.fail("multicast datagram was not received by the NatNet data socket")
        finally:
            sender.close()
            data_socket.close()
        self.assertEqual(data, b"frame")


if __name__ == "__main__":
    unittest.main()
