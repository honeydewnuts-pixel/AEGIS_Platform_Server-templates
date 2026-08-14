"""
Project: AEGIS
Company: Honeydewnuts Nigerian Limited

Purpose:
Image Upload and Image Processing API
"""

from fastapi import APIRouter
from fastapi import File
from fastapi import HTTPException
from fastapi import UploadFile

from app.schemas.image_processing import ImageInformationResponse
from app.services.image_processing_service import ImageProcessingService
from app.services.upload_service import UploadService

router = APIRouter(
    prefix="/upload",
    tags=["Image Upload"]
)

upload_service = UploadService()
image_service = ImageProcessingService()


@router.post("/")
async def upload_image(
    file: UploadFile = File(...)
):
    # Guard against None content_type (some clients / proxies omit it).
    # Real validation is extension + successful write in UploadService.
    ct = (file.content_type or "").split(";")[0].strip().lower()
    if ct and not ct.startswith("image/") and ct != "application/octet-stream":
        raise HTTPException(
            status_code=400,
            detail=f"Only image files are accepted (got content-type={file.content_type!r}).",
        )

    try:
        metadata = await upload_service.save_image(file)
        return metadata.model_dump()
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


@router.get(
    "/info/{filename}",
    response_model=ImageInformationResponse
)
async def image_information(filename: str):

    image_path = f"uploads/{filename}"

    try:
        image = image_service.load_image(image_path)

        information = image_service.image_information(image)

        return ImageInformationResponse(
            filename=filename,
            width=information["width"],
            height=information["height"],
            channels=information["channels"],
            status="success"
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Image not found."
        )

    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )
