"""
====================================================================
Project : AEGIS
System  : Autonomous Enterprise Global Intelligence System
Company : Honeydewnuts Nigerian Limited

File    : chart_detection.py

Purpose :
Pydantic schemas for the Chart Detection Engine.

These models define the request and response contracts for chart
detection and provide strong typing for downstream computer vision
modules.

Current Stage:
CP-004 – Batch 2
====================================================================
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ChartDetectionRequest(BaseModel):
    """
    Request model for chart detection.
    """

    image_path: str = Field(
        ...,
        description="Path to the preprocessed image."
    )


class ImageDimensions(BaseModel):
    """
    Image dimensions and metadata.
    """

    width: int = Field(..., ge=1)

    height: int = Field(..., ge=1)

    channels: int = Field(..., ge=1)


class ChartRegion(BaseModel):
    """
    Bounding coordinates of the detected chart.
    """

    left: int = Field(..., ge=0)

    top: int = Field(..., ge=0)

    right: int = Field(..., ge=0)

    bottom: int = Field(..., ge=0)


class PlottingArea(BaseModel):
    """
    Interior plotting region where candlesticks are drawn.
    """

    x: int = Field(..., ge=0)

    y: int = Field(..., ge=0)

    width: int = Field(..., ge=1)

    height: int = Field(..., ge=1)


class CandlestickInput(BaseModel):
    """
    Output passed to the Candlestick Recognition Engine.
    """

    image_path: str

    plotting_area: PlottingArea


class ChartDetectionResponse(BaseModel):
    """
    Complete chart detection response.
    """

    status: str = "success"

    timestamp: datetime = Field(
        default_factory=datetime.utcnow
    )

    image: ImageDimensions

    chart_region: ChartRegion

    plotting_area: PlottingArea

    candlestick_input: CandlestickInput

    message: Optional[str] = None
