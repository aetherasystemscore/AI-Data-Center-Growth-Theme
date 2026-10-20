"""Structured logging configuration that never leaks API credentials."""
from __future__ import annotations

import logging
import re
from core.config import LOGS_DIR


_SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key\s*=\s*)([^\s&\"']+)", re.IGNORECASE),
    re.compile(r"(Bearer\s+)([A-Za-z0-9._\-]+)", re.IGNORECASE),
    re.compile(r"(AIza[0-9A-Za-z_\-]{20,})"),
    re.compile(r"(sk-[0-9A-Za-z_\-]{16,})"),
]


class SecretRedactingFilter(logging.Filter):
    """Redacts API keys and tokens from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        redacted = msg
        for pat in _SECRET_PATTERNS:
            if pat.groups == 2:
                redacted = pat.sub(r"\1[REDACTED]", redacted)
            else:
                redacted = pat.sub("[REDACTED_KEY]", redacted)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def get_logger(name: str = "ai3") -> logging.Logger:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    stream_handler.addFilter(SecretRedactingFilter())

    file_handler = logging.FileHandler(LOGS_DIR / "ai3.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.addFilter(SecretRedactingFilter())

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    return logger
