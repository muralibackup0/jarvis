"""Rotating log at data/logs/jarvis.log - every action Jarvis takes is recorded here."""
import logging
import logging.handlers

from .. import config

_configured = False


def get_logger(name="jarvis"):
    global _configured
    if not _configured:
        handler = logging.handlers.RotatingFileHandler(
            config.LOG_DIR / "jarvis.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        root = logging.getLogger("jarvis")
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        _configured = True
    return logging.getLogger(name if name.startswith("jarvis") else f"jarvis.{name}")
