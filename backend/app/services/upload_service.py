"""
Project: AEGIS
Company: Honeydewnuts Nigerian Limited

Upload Service
"""

from pathlib import Path
from datetime import datetime
from uuid import uuid4

from fastapi import UploadFile

from app.models.image_metadata import ImageMetadata
from app.utils.file_validation import is_allowed_extension


UPLOAD_DIRECTORY = Path("uploads")


class UploadService:

    def __init__(self):
        UPLOAD_DIRECTORY.mkdir(exist_ok=True)

    async def save_image(self, file: UploadFile):

        if not is_allowed_extension(file.filename):
            raise ValueError("Unsupported file format.")

        extension = Path(file.filename).suffix.lower()

        generated_name = f"{uuid4()}{extension}"

        destination = UPLOAD_DIRECTORY / generated_name

        contents = await file.read()

        destination.write_bytes(contents)

        metadata = ImageMetadata(
            filename=generated_name,
            original_filename=file.filename,
            content_type=file.content_type,
            file_size=len(contents),
            upload_time=datetime.utcnow(),
            storage_path=str(destination)
        )

        return metadata
