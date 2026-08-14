"""
Project: AEGIS
Company: Honeydewnuts Nigerian Limited

Upload Schemas
"""

from datetime import datetime

from pydantic import BaseModel


class UploadResponse(BaseModel):

    filename: str

    original_filename: str

    content_type: str

    file_size: int

    upload_time: datetime

    storage_path: str
