"""Minimal structured console logger shared by every subsystem."""

from __future__ import annotations

import logging
import os
import sys

_LEVEL = os.environ.get("MNEMOSYNE_LOG_LEVEL", "INFO").upper()
_CONFIGURED = False


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    )
    root = logging.getLogger("mnemosyne")
    root.setLevel(_LEVEL)
    root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(f"mnemosyne.{name}")


def set_level(level: str) -> None:
    _configure()
    logging.getLogger("mnemosyne").setLevel(level.upper())
