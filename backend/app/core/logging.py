"""
Project: AEGIS
Company: Honeydewnuts Nigerian Limited

Purpose:
Central logging configuration. Safe to call repeatedly - reuses the
same handlers instead of stacking new ones on every call.
"""

import logging

_configured = False


def configure_logging(name: str | None = None) -> logging.Logger:
    """
    Configure (once) and return a logger.

    Parameters
    ----------
    name:
        Optional logger name, typically __name__ of the caller.
        Defaults to the root "AEGIS" logger if omitted, so existing
        call sites that use configure_logging() with no args keep working.
    """
    global _configured

    if not _configured:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
        _configured = True

    return logging.getLogger(name or "AEGIS")
