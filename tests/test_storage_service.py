import os
import tempfile
import unittest

from PyQt5.QtCore import QThread

from models.storage_models import AppSettings, ConnectionEntry
from services.storage_service import StorageService


class StorageServiceTests(unittest.TestCase):
    def test_thread_affinity_remains_on_calling_thread(self):
        storage = StorageService()
        calling_thread = QThread.currentThread()

        self.assertEqual(storage.thread(), calling_thread)

        storage.start()
        self.assertEqual(storage.status.name, "RUNNING")
        self.assertEqual(storage.thread(), calling_thread)

        storage.stop()
        self.assertEqual(storage.status.name, "STOPPED")
        self.assertEqual(storage.thread(), calling_thread)

    def test_settings_and_connections_persist_to_disk(self):
        with tempfile.TemporaryDirectory() as storage_dir:
            storage = StorageService(storage_dir=storage_dir)
            storage.on_start()

            settings = AppSettings(
                zoom_sensitivity=2.5,
                input_type="WASD",
                default_connection_string="udpout:127.0.0.1:14550",
                source_system_id=42,
            )
            storage.update_settings(settings)

            entry = ConnectionEntry(
                name="Drone-1",
                connection_string="udpin:0.0.0.0:14550",
                system_id=7,
                linked_object_name="Test Box",
            )
            self.assertTrue(storage.create_connection(entry))

            self.assertTrue(os.path.exists(os.path.join(storage_dir, "settings.json")))
            self.assertTrue(os.path.exists(os.path.join(storage_dir, "connections.json")))

            loaded_settings = StorageService.load_settings_from_disk(storage_dir)
            loaded_connections = StorageService.load_connections_from_disk(storage_dir)

            self.assertEqual(loaded_settings.zoom_sensitivity, 2.5)
            self.assertEqual(loaded_settings.input_type, "WASD")
            self.assertEqual(loaded_settings.source_system_id, 42)
            self.assertEqual(len(loaded_connections), 1)
            self.assertEqual(loaded_connections[0].name, "Drone-1")
            self.assertEqual(loaded_connections[0].system_id, 7)

    def test_export_and_import_round_trip(self):
        with tempfile.TemporaryDirectory() as storage_dir, tempfile.TemporaryDirectory() as import_dir:
            source = StorageService(storage_dir=storage_dir)
            source.on_start()
            source.update_settings(AppSettings(input_type="Arrow Keys", input_sensitivity=1.7))
            source.create_connection(
                ConnectionEntry(name="Drone-2", connection_string="serial:/dev/ttyUSB0:57600")
            )

            export_path = os.path.join(storage_dir, "export.json")
            self.assertTrue(source.export_to_file(export_path))

            destination = StorageService(storage_dir=import_dir)
            destination.on_start()
            self.assertTrue(destination.import_from_file(export_path))

            self.assertEqual(destination.get_settings().input_type, "Arrow Keys")
            self.assertAlmostEqual(destination.get_settings().input_sensitivity, 1.7)
            imported = destination.get_connection("Drone-2")
            self.assertIsNotNone(imported)
            self.assertEqual(imported.connection_string, "serial:/dev/ttyUSB0:57600")


if __name__ == "__main__":
    unittest.main()
