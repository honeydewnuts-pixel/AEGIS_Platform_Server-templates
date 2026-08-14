"""
Project: AEGIS
Company: Honeydewnuts Nigerian Limited

Purpose:
Shared helper functions for image information.
"""

from pathlib import Path


def file_extension(path: str):

    return Path(path).suffix.lower()


def file_name(path: str):

    return Path(path).name
