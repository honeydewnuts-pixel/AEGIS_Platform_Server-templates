"""
Project: AEGIS
Company: Honeydewnuts Nigerian Limited

Image Metadata Model
"""

from datetime import datetime
from pydantic import BaseModel


class ImageMetadata(BaseModel):
    filename: str
    original_filename: str
    content_type: str
    file_size: int
    upload_time: datetime
    storage_path: str
