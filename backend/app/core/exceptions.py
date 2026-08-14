"""
Project: AEGIS
Company: Honeydewnuts Nigerian Limited

Purpose:
Custom exceptions for AEGIS.
"""


class AEGISException(Exception):
    """Base exception."""


class InvalidImageException(AEGISException):
    """Invalid image."""


class ImageNotFoundException(AEGISException):
    """Image not found."""
