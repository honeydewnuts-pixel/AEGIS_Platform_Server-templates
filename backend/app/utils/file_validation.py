"""
Project: AEGIS
Company: Honeydewnuts Nigerian Limited

File Validation Utilities
"""

from pathlib import Path

ALLOWED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".webp"
}


def is_allowed_extension(filename: str) -> bool:

    extension = Path(filename).suffix.lower()

    return extension in ALLOWED_EXTENSIONS
