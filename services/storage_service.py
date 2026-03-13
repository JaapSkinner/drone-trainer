"""Persistent storage service.

Provides JSON file–based persistence for application settings and MAVLink
connection configurations.  Storage files live in a ``storage_data/``
directory next to the application root.

Usage::

    storage = StorageService()
    storage.start()

    # Settings (single-object, read/update)
    settings = storage.get_settings()
    settings.zoom_sensitivity = 2.0
    storage.update_settings(settings)

    # Connections (multi-object CRUD)
    entry = ConnectionEntry(name="Drone-1", connection_string="udpin:0.0.0.0:14550")
    storage.create_connection(entry)
    storage.get_connection("Drone-1")
    storage.update_connection(entry)
    storage.delete_connection("Drone-1")
    storage.list_connections()
"""

import json
import os
from typing import Dict, List, Optional

from PyQt5.QtCore import pyqtSignal

from services.service_base import ServiceBase, DebugLevel, ServiceLevel
from models.storage_models import AppSettings, ConnectionEntry


# Default storage directory (relative to the working directory)
_STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "storage_data")
_SETTINGS_FILE = "settings.json"
_CONNECTIONS_FILE = "connections.json"


class StorageService(ServiceBase):
    """Service for persisting application state to JSON files.

    Signals:
        settings_updated: Emitted after settings are written to disk.
        connections_updated: Emitted after the connections list changes on disk.
    """

    settings_updated = pyqtSignal()
    connections_updated = pyqtSignal()

    def __init__(self, storage_dir: str = None, debug_level: DebugLevel = None):
        super().__init__(debug_level=debug_level or DebugLevel.LOG)
        self._storage_dir = storage_dir or _STORAGE_DIR
        self._settings: AppSettings = AppSettings()
        self._connections: Dict[str, ConnectionEntry] = {}

    # ------------------------------------------------------------------
    # ServiceBase lifecycle
    # ------------------------------------------------------------------

    def on_start(self):
        """Load data from disk on service start."""
        os.makedirs(self._storage_dir, exist_ok=True)
        self._load_settings()
        self._load_connections()
        self.set_status(ServiceLevel.RUNNING, "Storage: Ready")

    def on_stop(self):
        """Nothing to clean up – all writes are immediate."""
        pass

    def update(self):
        """No periodic work needed."""
        pass

    # ------------------------------------------------------------------
    # Settings CRUD (single-object: read / update)
    # ------------------------------------------------------------------

    def get_settings(self) -> AppSettings:
        """Return the current in-memory settings (already loaded from disk)."""
        return self._settings

    def update_settings(self, settings: AppSettings) -> None:
        """Replace the current settings and write to disk.

        Args:
            settings: New application settings to persist.
        """
        self._settings = settings
        self._save_settings()
        self.settings_updated.emit()

    # ------------------------------------------------------------------
    # Connections CRUD (multi-object)
    # ------------------------------------------------------------------

    def create_connection(self, entry: ConnectionEntry) -> bool:
        """Add a new connection entry to persistent storage.

        Args:
            entry: Connection configuration to store.

        Returns:
            True if created, False if a connection with the same name
            already exists.
        """
        if entry.name in self._connections:
            return False
        self._connections[entry.name] = entry
        self._save_connections()
        self.connections_updated.emit()
        return True

    def get_connection(self, name: str) -> Optional[ConnectionEntry]:
        """Retrieve a stored connection by name.

        Args:
            name: Unique connection name.

        Returns:
            The ``ConnectionEntry`` or ``None`` if not found.
        """
        return self._connections.get(name)

    def list_connections(self) -> List[ConnectionEntry]:
        """Return all stored connections.

        Returns:
            List of ``ConnectionEntry`` objects.
        """
        return list(self._connections.values())

    def update_connection(self, entry: ConnectionEntry) -> bool:
        """Update an existing connection entry on disk.

        Args:
            entry: Updated connection configuration.  The ``name`` field
                identifies which entry to overwrite.

        Returns:
            True if updated, False if not found.
        """
        if entry.name not in self._connections:
            return False
        self._connections[entry.name] = entry
        self._save_connections()
        self.connections_updated.emit()
        return True

    def upsert_connection(self, entry: ConnectionEntry) -> None:
        """Create or update a connection entry.

        Convenience wrapper used when the caller does not care whether the
        entry already exists (e.g. auto-saving after a successful connect).

        Args:
            entry: Connection configuration to create or update.
        """
        self._connections[entry.name] = entry
        self._save_connections()
        self.connections_updated.emit()

    def delete_connection(self, name: str) -> bool:
        """Remove a connection entry from persistent storage.

        Args:
            name: Unique connection name.

        Returns:
            True if deleted, False if not found.
        """
        if name not in self._connections:
            return False
        del self._connections[name]
        self._save_connections()
        self.connections_updated.emit()
        return True

    # ------------------------------------------------------------------
    # Internal I/O helpers
    # ------------------------------------------------------------------

    def _settings_path(self) -> str:
        return os.path.join(self._storage_dir, _SETTINGS_FILE)

    def _connections_path(self) -> str:
        return os.path.join(self._storage_dir, _CONNECTIONS_FILE)

    def _load_settings(self) -> None:
        path = self._settings_path()
        if not os.path.exists(path):
            self._settings = AppSettings()
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._settings = AppSettings.from_dict(data)
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            print(f"[StorageService] WARNING: Could not parse {path}: {exc}")
            self._settings = AppSettings()

    def _save_settings(self) -> None:
        path = self._settings_path()
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self._settings.to_dict(), fh, indent=2)
        except OSError as exc:
            print(f"[StorageService] ERROR: Could not write {path}: {exc}")

    def _load_connections(self) -> None:
        path = self._connections_path()
        if not os.path.exists(path):
            self._connections = {}
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._connections = {}
            for item in data:
                entry = ConnectionEntry.from_dict(item)
                self._connections[entry.name] = entry
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            print(f"[StorageService] WARNING: Could not parse {path}: {exc}")
            self._connections = {}

    def _save_connections(self) -> None:
        path = self._connections_path()
        try:
            entries = [e.to_dict() for e in self._connections.values()]
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(entries, fh, indent=2)
        except OSError as exc:
            print(f"[StorageService] ERROR: Could not write {path}: {exc}")
