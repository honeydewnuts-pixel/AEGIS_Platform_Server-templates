"""
Project: AEGIS
Company: Honeydewnuts Nigerian Limited

Purpose:
Upload configuration.
"""

from pathlib import Path

UPLOAD_DIRECTORY = Path("uploads")

UPLOAD_DIRECTORY.mkdir(
    parents=True,
    exist_ok=True
)

MAX_UPLOAD_SIZE = 20 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".webp"
}
