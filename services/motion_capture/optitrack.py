"""OptiTrack (Motive) source using the vendored NatNet SDK client.

NatNet identifies rigid bodies by numeric ID in each frame; their names come
from separate model-definition messages. This adapter keeps an ID → name map
(re-requesting definitions when Motive reports a change or an unknown ID
appears) so subjects are matched to scene objects by *name*, exactly like
Vicon subjects.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, Optional

from models import frames

logger = logging.getLogger(__name__)

# Called from the NatNet receive thread with (subject name, scene pose, monotonic time).
SampleCallback = Callable[[str, tuple, float], None]


def _decode_name(name) -> str:
    if isinstance(name, (bytes, bytearray)):
        return name.decode("utf-8", errors="replace").strip("\x00 ")
    return str(name).strip()


class OptiTrackSource:
    MODEL_REQUEST_MIN_INTERVAL_S = 1.0

    def __init__(self, on_sample: SampleCallback, server_ip: str = "127.0.0.1",
                 client_ip: str = "127.0.0.1", multicast: bool = True, up_axis: str = "y"):
        self._on_sample = on_sample
        self.server_ip = server_ip
        self.client_ip = client_ip
        self.multicast = multicast
        self.up_axis = up_axis
        self._client = None
        self._names: Dict[int, str] = {}
        self._names_lock = threading.Lock()
        self._last_model_request = 0.0

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> Optional[str]:
        """Start receiving. Returns None on success, or an error message."""
        from services.motion_capture.natnet.NatNetClient import NatNetClient

        client = NatNetClient()
        client.set_client_address(self.client_ip)
        client.set_server_address(self.server_ip)
        client.set_use_multicast(self.multicast)
        client.set_print_level(0)
        client.new_frame_with_data_listener = self.handle_frame
        client.data_descriptions_listener = self.handle_descriptions
        try:
            # The SDK calls sys.exit() when it can't bind its sockets.
            started = client.run("d")
        except (SystemExit, OSError) as exc:
            return f"could not open NatNet sockets ({exc})"
        if not started:
            return "could not open NatNet sockets"
        self._client = client
        self._request_models(force=True)
        return None

    def stop(self):
        client, self._client = self._client, None
        if client is not None:
            try:
                client.shutdown()
            except Exception:
                logger.exception("Error shutting down NatNet client")

    def connected(self) -> bool:
        return self._client is not None and self._client.connected()

    # -- NatNet callbacks (run on the SDK's receive thread) -------------------

    def handle_descriptions(self, data_descs):
        names = {}
        for desc in getattr(data_descs, "rigid_body_list", []):
            names[int(desc.id_num)] = _decode_name(desc.sz_name)
        with self._names_lock:
            self._names.update(names)
        logger.info("OptiTrack rigid bodies: %s", ", ".join(sorted(names.values())) or "none")

    def handle_frame(self, data_dict):
        if data_dict.get("tracked_models_changed"):
            self._request_models(force=True)
        mocap_data = data_dict.get("mocap_data")
        rigid_bodies = getattr(getattr(mocap_data, "rigid_body_data", None), "rigid_body_list", [])
        now = time.monotonic()
        for rb in rigid_bodies:
            if not getattr(rb, "tracking_valid", True):
                continue  # occluded this frame
            with self._names_lock:
                name = self._names.get(rb.id_num)
            if name is None:
                self._request_models()
                name = f"rigid_body_{rb.id_num}"
            pose = frames.optitrack_to_scene_pose(rb.pos, rb.rot, self.up_axis)
            self._on_sample(name, pose, now)

    def _request_models(self, force: bool = False):
        now = time.monotonic()
        if self._client is None:
            return
        if not force and now - self._last_model_request < self.MODEL_REQUEST_MIN_INTERVAL_S:
            return
        self._last_model_request = now
        try:
            self._client.request_model_definitions()
        except OSError as exc:
            logger.warning("NatNet model definition request failed: %s", exc)
