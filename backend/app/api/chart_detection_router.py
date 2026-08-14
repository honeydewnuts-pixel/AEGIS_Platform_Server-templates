"""
====================================================================
Project : AEGIS
System  : Autonomous Enterprise Global Intelligence System
Company : Honeydewnuts Nigerian Limited

File    : chart_detection_router.py

Purpose :
FastAPI router for the Chart Detection Engine.

Current Stage:
CP-004 – Batch 3
====================================================================
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.schemas.chart_detection import (
    ChartDetectionRequest,
    ChartDetectionResponse,
)
from app.services.chart_detection_service import ChartDetectionService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chart-detection",
    tags=["Chart Detection"],
)

service = ChartDetectionService()


@router.post(
    "/detect",
    response_model=ChartDetectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Detect the chart region from a preprocessed image",
)
async def detect_chart(
    request: ChartDetectionRequest,
) -> ChartDetectionResponse:
    """
    Detect the chart region and plotting area.

    This endpoint prepares the image for the Candlestick Recognition
    Engine by locating the chart boundaries and plotting area.
    """

    try:
        logger.info(
            "Chart detection requested for image: %s",
            request.image_path,
        )

        result = service.detect(request.image_path)

        logger.info("Chart detection completed successfully.")

        return result

    except FileNotFoundError as exc:
        logger.exception("Image file not found.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        logger.exception("Chart detection validation failed.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception("Unexpected chart detection error.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from exc
