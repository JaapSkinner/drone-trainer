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
from dataclasses import fields

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
        # No thread affinity tweaks here — ServiceBase manages the service
        # thread. For synchronous startup needs, use the static loader
        # helpers below so the UI can read persisted state before starting
        # threaded services.
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

    def import_from_file(self, file_path: str) -> bool:
        """Import settings and/or connections from a JSON file.

        The file may contain:
          - a dict with AppSettings fields (will replace current settings),
          - a dict with a 'connections' key containing a list of connection dicts,
          - a top-level list which will be treated as connections.

        Returns True on success, False on error.
        """
        if not os.path.exists(file_path):
            print(f"[StorageService] ERROR: Import file not found: {file_path}")
            return False

        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:
            print(f"[StorageService] ERROR: Failed to parse import file: {exc}")
            return False

        try:
            # If it's a list, treat as connections list
            if isinstance(data, list):
                for item in data:
                    try:
                        entry = ConnectionEntry.from_dict(item)
                        self.upsert_connection(entry)
                    except Exception:
                        continue
                return True

            # If dict contains 'connections', import them
            if isinstance(data, dict):
                # If caller exported via export_to_file, settings may be nested under 'settings'
                if 'settings' in data and isinstance(data['settings'], dict):
                    try:
                        sdict = data['settings']
                        settings = AppSettings.from_dict(sdict)
                        self.update_settings(settings)
                    except Exception as e:
                        print(f"[StorageService] WARNING: Could not import nested settings: {e}")

                # Import settings if present (or if dict looks like settings)
                # Heuristic: if any AppSettings field exists in the dict, treat it as settings
                settings_keys = {f.name for f in fields(AppSettings)}
                if any(k in data for k in settings_keys):
                    try:
                        sdict = {k: v for k, v in data.items() if k in settings_keys}
                        settings = AppSettings.from_dict(sdict)
                        self.update_settings(settings)
                    except Exception as e:
                        print(f"[StorageService] WARNING: Could not import settings: {e}")

                # Import connections key if present
                if 'connections' in data and isinstance(data['connections'], list):
                    for item in data['connections']:
                        try:
                            entry = ConnectionEntry.from_dict(item)
                            self.upsert_connection(entry)
                        except Exception:
                            continue

                return True

        except Exception as exc:
            print(f"[StorageService] ERROR: Import failed: {exc}")
            return False

        return False

    def export_to_file(self, file_path: str) -> bool:
        """Export current settings and connections to a JSON file.

        Writes a dict with keys 'settings' (full AppSettings dict) and
        'connections' (list of connection dicts).
        Returns True on success, False on error.
        """
        try:
            data = {
                'settings': self._settings.to_dict(),
                'connections': [c.to_dict() for c in self._connections.values()]
            }
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path) or '.', exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as fh:
                json.dump(data, fh, indent=2)
            return True
        except Exception as exc:
            print(f"[StorageService] ERROR: Failed to export to {file_path}: {exc}")
            return False

    # ------------------------------------------------------------------
    # Synchronous file-based loaders (safe to call from main thread)
    # ------------------------------------------------------------------
    @staticmethod
    def load_settings_from_disk(storage_dir: str = None) -> AppSettings:
        """Load AppSettings directly from disk without constructing the service.

        This is intended for synchronous startup where the UI needs
        persisted settings before threaded services are started.
        """
        _dir = storage_dir or _STORAGE_DIR
        path = os.path.join(_dir, _SETTINGS_FILE)
        if not os.path.exists(path):
            return AppSettings()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return AppSettings.from_dict(data)
        except (json.JSONDecodeError, TypeError, KeyError, OSError) as exc:
            print(f"[StorageService] WARNING: Could not parse {path}: {exc}")
            return AppSettings()

    @staticmethod
    def load_connections_from_disk(storage_dir: str = None) -> List[ConnectionEntry]:
        """Load connection entries directly from disk as a list.

        Returns an empty list on error or if no file exists.
        """
        _dir = storage_dir or _STORAGE_DIR
        path = os.path.join(_dir, _CONNECTIONS_FILE)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            entries: List[ConnectionEntry] = []
            for item in data:
                try:
                    entries.append(ConnectionEntry.from_dict(item))
                except Exception:
                    continue
            return entries
        except (json.JSONDecodeError, TypeError, KeyError, OSError) as exc:
            print(f"[StorageService] WARNING: Could not parse {path}: {exc}")
            return []

