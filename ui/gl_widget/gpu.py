"""GPU resources for the renderer: shader programs and vertex buffers.

Everything here needs a current GL context; create and use it only from
``SceneRenderer`` (``initializeGL`` / ``paintGL``).

* :class:`Program` compiles a GLSL 1.20 program (OpenGL 2.1, so it runs on
  any lab PC and in the headless test context) and caches uniform locations.
* :class:`BufferCache` uploads each static :class:`~models.render_items.Mesh`
  or :class:`~models.render_items.Lines` once and deletes its buffer after the
  geometry object is garbage collected (or released). Collection can happen on
  any thread, so deletions are queued and carried out by :meth:`flush` at the
  start of the next frame, when the context is current.
"""
import threading
import weakref

import numpy as np
from OpenGL.GL import (GL_ARRAY_BUFFER, GL_COMPILE_STATUS, GL_FRAGMENT_SHADER, GL_LINK_STATUS,
                       GL_STATIC_DRAW, GL_TRUE, GL_VERTEX_SHADER, glAttachShader, glBindAttribLocation,
                       glBindBuffer, glBufferData, glCompileShader, glCreateProgram, glCreateShader,
                       glDeleteBuffers, glDeleteShader, glGenBuffers, glGetProgramInfoLog, glGetProgramiv,
                       glGetShaderInfoLog, glGetShaderiv, glGetUniformLocation, glLinkProgram, glShaderSource,
                       glUniform1f, glUniform3f, glUniform4f, glUniformMatrix3fv, glUniformMatrix4fv,
                       glUseProgram)


class ShaderError(RuntimeError):
    pass


def _compile(kind, source):
    shader = glCreateShader(kind)
    glShaderSource(shader, source)
    glCompileShader(shader)
    if glGetShaderiv(shader, GL_COMPILE_STATUS) != GL_TRUE:
        log = glGetShaderInfoLog(shader)
        raise ShaderError(log.decode(errors="replace") if isinstance(log, bytes) else str(log))
    return shader


class Program:
    def __init__(self, vertex_source: str, fragment_source: str, attributes: dict):
        vs = _compile(GL_VERTEX_SHADER, vertex_source)
        fs = _compile(GL_FRAGMENT_SHADER, fragment_source)
        self.handle = glCreateProgram()
        glAttachShader(self.handle, vs)
        glAttachShader(self.handle, fs)
        for name, location in attributes.items():
            glBindAttribLocation(self.handle, location, name)
        glLinkProgram(self.handle)
        glDeleteShader(vs)
        glDeleteShader(fs)
        if glGetProgramiv(self.handle, GL_LINK_STATUS) != GL_TRUE:
            log = glGetProgramInfoLog(self.handle)
            raise ShaderError(log.decode(errors="replace") if isinstance(log, bytes) else str(log))
        self.attributes = dict(attributes)
        self._uniforms = {}

    def use(self):
        glUseProgram(self.handle)

    def location(self, name: str) -> int:
        loc = self._uniforms.get(name)
        if loc is None:
            loc = self._uniforms[name] = glGetUniformLocation(self.handle, name)
        return loc

    # Setters take row-major numpy matrices (GL is told to transpose them).
    def set_mat4(self, name, matrix):
        glUniformMatrix4fv(self.location(name), 1, GL_TRUE, matrix)

    def set_mat3(self, name, matrix):
        glUniformMatrix3fv(self.location(name), 1, GL_TRUE, matrix)

    def set_vec4(self, name, v):
        glUniform4f(self.location(name), *v)

    def set_vec3(self, name, v):
        glUniform3f(self.location(name), *v)

    def set_float(self, name, value):
        glUniform1f(self.location(name), value)


def _forget(cache_ref, key):
    cache = cache_ref()
    if cache is not None:
        cache._forget(key)


class BufferCache:
    """Static geometry → GL vertex buffer, created on first use."""

    def __init__(self):
        self._lock = threading.Lock()
        self._buffers = {}    # id(geometry) → (buffer id, weakref.finalize)
        self._pending = []    # buffer ids to delete on the GL thread

    def buffer_for(self, geometry, make_data) -> int:
        """The buffer holding ``geometry``; ``make_data()`` gives the array to upload the first time."""
        key = id(geometry)
        with self._lock:
            entry = self._buffers.get(key)
        if entry is not None:
            return entry[0]
        data = np.ascontiguousarray(make_data(), dtype=np.float32)
        buffer = int(glGenBuffers(1))
        glBindBuffer(GL_ARRAY_BUFFER, buffer)
        glBufferData(GL_ARRAY_BUFFER, data.nbytes, data, GL_STATIC_DRAW)
        finalizer = weakref.finalize(geometry, _forget, weakref.ref(self), key)
        finalizer.atexit = False
        with self._lock:
            self._buffers[key] = (buffer, finalizer)
        return buffer

    def release(self, geometry):
        """Free ``geometry``'s buffer at the next frame (it is re-uploaded if drawn again)."""
        with self._lock:
            entry = self._buffers.get(id(geometry))
        if entry is not None:
            entry[1]()   # runs _forget once and detaches the finalizer

    def _forget(self, key):
        with self._lock:
            entry = self._buffers.pop(key, None)
            if entry is not None:
                self._pending.append(entry[0])

    def flush(self):
        """Delete buffers of geometry that has gone away (context must be current)."""
        with self._lock:
            pending, self._pending = self._pending, []
        if pending:
            glDeleteBuffers(len(pending), pending)

    def reset(self):
        """Forget every buffer without deleting it (its context was destroyed)."""
        with self._lock:
            entries, self._buffers, self._pending = list(self._buffers.values()), {}, []
        for _, finalizer in entries:
            finalizer.detach()

    @property
    def live_count(self) -> int:
        with self._lock:
            return len(self._buffers)
