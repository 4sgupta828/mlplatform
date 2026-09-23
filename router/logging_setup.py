"""Structured logging setup (dev-task convention: logger support)."""

from __future__ import annotations

import logging


def configure_logging(level: str = "WARNING") -> logging.Logger:
    """Configure the ``router`` logger tree and return the root ``router`` logger.

    Logs go to stderr so they never contaminate table/JSON output on stdout.
    """
    numeric = getattr(logging, str(level).upper(), None)
    if not isinstance(numeric, int):
        raise ValueError(f"invalid log level: {level!r}")

    logger = logging.getLogger("router")
    logger.setLevel(numeric)

    # Avoid duplicate handlers if called more than once.
    if not logger.handlers:
        handler = logging.StreamHandler()  # stderr by default
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
        )
        logger.addHandler(handler)
    else:
        for h in logger.handlers:
            h.setLevel(numeric)

    logger.propagate = False
    return logger
