"""
Project: AEGIS
Company: Honeydewnuts Nigerian Limited

Purpose:
Image Preprocessing API

Provides endpoints for executing the AEGIS Vision
Preprocessing Engine independently of the upload API.
"""

from fastapi import APIRouter
from fastapi import HTTPException

from app.schemas.image_preprocessing import (
    ImagePreprocessingRequest,
    ImagePreprocessingResponse,
)
from app.services.preprocessing_executor import (
    VisionPreprocessingExecutor,
)

router = APIRouter(
    prefix="/preprocessing",
    tags=["Vision Preprocessing"],
)

executor = VisionPreprocessingExecutor()


@router.post(
    "/execute",
    response_model=ImagePreprocessingResponse,
)
async def execute_preprocessing(
    request: ImagePreprocessingRequest,
) -> ImagePreprocessingResponse:
    """
    Execute the Vision Preprocessing pipeline.

    Parameters
    ----------
    request
        Image preprocessing request.

    Returns
    -------
    ImagePreprocessingResponse
    """

    try:

        return executor.execute(request)

    except FileNotFoundError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error),
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception as error:

        executor.logger.exception(
            "Vision preprocessing pipeline failed."
        )

        raise HTTPException(
            status_code=500,
            detail="Vision preprocessing failed.",
        ) from error
