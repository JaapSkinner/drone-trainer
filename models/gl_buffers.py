"""OpenGL buffers for mesh geometry, with deferred deletion.

GL objects belong to a context and can only be created or deleted while it is
current, but scene objects are created and removed from UI code at any time.
So uploads happen lazily on first draw, and deletions are queued and carried
out by the renderer at the start of the next frame.

If the GL context is recreated (Qt does this when a QOpenGLWidget is moved to
another window), call :func:`begin_context` from ``initializeGL``; buffers made
in the old context are then re-uploaded on their next draw.
"""
import ctypes
import threading

import numpy as np
from OpenGL.GL import (GL_ARRAY_BUFFER, GL_FLOAT, GL_LINES, GL_NORMAL_ARRAY,
                       GL_STATIC_DRAW, GL_TRIANGLES, GL_VERTEX_ARRAY,
                       GL_COLOR_ARRAY, glBindBuffer, glBufferData,
                       glColorPointer, glDeleteBuffers, glDisableClientState,
                       glDrawArrays, glEnableClientState, glGenBuffers,
                       glNormalPointer, glVertexPointer)

from models.mesh_data import MeshData

_lock = threading.Lock()
_pending_delete = []        # (context generation, buffer id)
_context_generation = 0
_live_buffers = 0


def begin_context():
    """Note that a new GL context is in use; buffers from the previous one are gone."""
    global _context_generation, _live_buffers
    with _lock:
        _context_generation += 1
        _pending_delete.clear()
        _live_buffers = 0


def flush_pending_deletes():
    """Delete queued buffers. Call with the GL context current (once per frame)."""
    global _live_buffers
    with _lock:
        if not _pending_delete:
            return
        ids = [buf for gen, buf in _pending_delete if gen == _context_generation]
        _pending_delete.clear()
    if ids:
        glDeleteBuffers(len(ids), np.array(ids, dtype=np.uint32))
        with _lock:
            _live_buffers -= len(ids)


def live_buffer_count() -> int:
    """Number of GL buffers currently allocated through this module."""
    with _lock:
        return _live_buffers


class MeshBuffer:
    """Draws a :class:`MeshData` with one ``glDrawArrays`` call.

    ``use_vbo=False`` keeps the data in client memory instead (sensible for
    tiny shared primitives such as the unit cube, which then never need
    cleaning up).
    """

    _STRIDE = 6 * 4  # position (3 floats) + normal (3 floats)

    def __init__(self, mesh: MeshData, use_vbo: bool = True):
        self.vertex_count = len(mesh.positions)
        self._use_vbo = use_vbo
        if use_vbo:
            self._interleaved = np.ascontiguousarray(
                np.hstack([mesh.positions, mesh.normals]).astype(np.float32))
        else:
            # Separate contiguous arrays: PyOpenGL would copy a strided view,
            # breaking the stride.
            self._positions = np.ascontiguousarray(mesh.positions, dtype=np.float32)
            self._normals = np.ascontiguousarray(mesh.normals, dtype=np.float32)
        self._vbo = None
        self._generation = None

    def _upload(self):
        global _live_buffers
        self._vbo = int(glGenBuffers(1))
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
        glBufferData(GL_ARRAY_BUFFER, self._interleaved.nbytes, self._interleaved, GL_STATIC_DRAW)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        self._generation = _context_generation
        with _lock:
            _live_buffers += 1

    def draw(self):
        """Draw the triangles using the current colour/material state."""
        if self.vertex_count == 0:
            return
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_NORMAL_ARRAY)
        try:
            if self._use_vbo:
                if self._vbo is None or self._generation != _context_generation:
                    self._upload()
                glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
                glVertexPointer(3, GL_FLOAT, self._STRIDE, ctypes.c_void_p(0))
                glNormalPointer(GL_FLOAT, self._STRIDE, ctypes.c_void_p(12))
                glDrawArrays(GL_TRIANGLES, 0, self.vertex_count)
                glBindBuffer(GL_ARRAY_BUFFER, 0)
            else:
                glVertexPointer(3, GL_FLOAT, 0, self._positions)
                glNormalPointer(GL_FLOAT, 0, self._normals)
                glDrawArrays(GL_TRIANGLES, 0, self.vertex_count)
        finally:
            glDisableClientState(GL_NORMAL_ARRAY)
            glDisableClientState(GL_VERTEX_ARRAY)

    def release(self):
        """Queue the GPU buffer for deletion (safe to call from any thread)."""
        if self._vbo is not None:
            with _lock:
                _pending_delete.append((self._generation, self._vbo))
            self._vbo = None
            self._generation = None


def draw_lines(points: np.ndarray, colours: np.ndarray = None):
    """Draw ``points`` (2N, 3) as GL_LINES from client memory, optionally per-vertex coloured."""
    if len(points) == 0:
        return
    glEnableClientState(GL_VERTEX_ARRAY)
    if colours is not None:
        glEnableClientState(GL_COLOR_ARRAY)
        glColorPointer(colours.shape[1], GL_FLOAT, 0, colours)
    try:
        glVertexPointer(3, GL_FLOAT, 0, points)
        glDrawArrays(GL_LINES, 0, len(points))
    finally:
        if colours is not None:
            glDisableClientState(GL_COLOR_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)
