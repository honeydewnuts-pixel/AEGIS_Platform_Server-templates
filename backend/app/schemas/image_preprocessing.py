"""
====================================================================
Project : AEGIS
System  : Autonomous Enterprise Global Intelligence System
Company : Honeydewnuts Nigerian Limited

File    : image_preprocessing.py

Purpose :
Pydantic schemas for the Vision Preprocessing Engine.

These schemas define the request and response contracts for
image preprocessing. They are intentionally generic so they
can be reused by future modules including:

    • Chart Detection
    • Candlestick Recognition
    • Indicator Recognition
    • OCR
    • Trading Intelligence

Current Stage:
CP-003 Part 1 – Batch 4
====================================================================
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ImagePreprocessingRequest(BaseModel):
    """
    Request for image preprocessing.
    """

    filename: str = Field(
        ...,
        description="Uploaded image filename."
    )

    apply_brightness: bool = Field(
        default=True,
        description="Apply brightness normalization."
    )

    apply_contrast: bool = Field(
        default=True,
        description="Apply contrast enhancement."
    )

    apply_grayscale: bool = Field(
        default=False,
        description="Convert image to grayscale."
    )

    resize_width: Optional[int] = Field(
        default=None,
        ge=1,
        description="Target width."
    )

    resize_height: Optional[int] = Field(
        default=None,
        ge=1,
        description="Target height."
    )


class PreprocessingStageResult(BaseModel):
    """
    Result for a single preprocessing stage.
    """

    stage_name: str

    executed: bool

    success: bool

    execution_time_ms: float = Field(
        default=0.0,
        ge=0.0
    )

    message: Optional[str] = None


class PipelineExecutionSummary(BaseModel):
    """
    Summary of pipeline execution.
    """

    total_stages: int

    successful_stages: int

    failed_stages: int

    total_execution_time_ms: float = Field(
        default=0.0,
        ge=0.0
    )


class ProcessingStatistics(BaseModel):
    """
    Image statistics after preprocessing.
    """

    width: int

    height: int

    channels: int

    file_size_bytes: Optional[int] = None

    color_space: str = "BGR"


class ImagePreprocessingResponse(BaseModel):
    """
    Complete preprocessing response.
    """

    status: str = "success"

    filename: str

    processed_filename: Optional[str] = None

    pipeline_version: str = "CP-003-Part1"

    timestamp: datetime = Field(
        default_factory=datetime.utcnow
    )

    statistics: ProcessingStatistics

    stages: List[PreprocessingStageResult]

    summary: PipelineExecutionSummary
