"""Filesystem locations used by the application."""
import os

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Set this to keep settings, scenes and logs somewhere other than
# <repo>/storage_data (the test suite does this to stay out of the repo).
DATA_DIR_ENV_VAR = "DRONE_TRAINER_DATA_DIR"


def data_dir() -> str:
    """Directory for persisted user data (settings, connections, scenes, logs)."""
    return os.environ.get(DATA_DIR_ENV_VAR) or os.path.join(APP_ROOT, "storage_data")
