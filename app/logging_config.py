"""
logging_config.py — Logger centralizado (reemplaza prints sueltos).
"""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def get_logger(name: str = "mission") -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        root = logging.getLogger("mission")
        if not root.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%H:%M:%S",
                )
            )
            root.addHandler(handler)
            root.setLevel(logging.INFO)
        _CONFIGURED = True
    return logging.getLogger(name if name.startswith("mission") else f"mission.{name}")
