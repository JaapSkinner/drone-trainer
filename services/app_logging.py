import logging
import os
import sys
from logging.handlers import RotatingFileHandler


_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "storage_data",
    "logs",
)
_LOG_FILE = "drone_trainer.log"
_LOGGING_CONFIGURED = False


class _StreamToLogger:
    """File-like stream object that forwards writes into logging."""

    def __init__(self, logger: logging.Logger, level: int):
        self._logger = logger
        self._level = level

    def write(self, buf):
        """Write stream data into logger records line by line."""
        if not isinstance(buf, str):
            buf = str(buf)
        text = buf.strip()
        if not text:
            return
        for line in text.splitlines():
            line = line.strip()
            if line:
                self._logger.log(self._level, line)

    def flush(self):
        pass


def get_log_file_path() -> str:
    return os.path.join(_LOG_DIR, _LOG_FILE)


def configure_logging(
    level: int = logging.INFO,
    redirect_stdio: bool = True,
    stream_to_stderr: bool = False,
) -> str:
    """Configure app-wide logging for file logging + optional stderr + redirected prints."""
    global _LOGGING_CONFIGURED
    root_logger = logging.getLogger()
    if _LOGGING_CONFIGURED:
        root_logger.setLevel(level)
        return get_log_file_path()

    os.makedirs(_LOG_DIR, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        get_log_file_path(),
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    if stream_to_stderr:
        stream_handler = logging.StreamHandler(stream=sys.__stderr__)
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)
        root_logger.addHandler(stream_handler)
    _LOGGING_CONFIGURED = True

    if redirect_stdio:
        stdio_logger = logging.getLogger("stdio")
        sys.stdout = _StreamToLogger(stdio_logger, logging.INFO)
        sys.stderr = _StreamToLogger(stdio_logger, logging.ERROR)

    root_logger.info("Logging configured. Log file: %s", get_log_file_path())
    return get_log_file_path()
