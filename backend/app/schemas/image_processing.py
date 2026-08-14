"""
Project: AEGIS
Company: Honeydewnuts Nigerian Limited

Purpose:
Schemas for image processing responses.
"""

from pydantic import BaseModel


class ImageInformationResponse(BaseModel):
    filename: str
    width: int
    height: int
    channels: int
    status: str
