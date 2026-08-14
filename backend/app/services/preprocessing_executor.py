"""
====================================================================
Project : AEGIS
System  : Autonomous Enterprise Global Intelligence System
Company : Honeydewnuts Nigerian Limited

File    : preprocessing_executor.py

Purpose :
Production preprocessing execution engine.

This service is responsible for:

    • Loading images
    • Executing preprocessing stages
    • Recording execution metrics
    • Producing schema-compliant responses
    • Logging pipeline execution
    • Graceful exception handling

Current Stage:
CP-003 Part 2 – Batch 1
====================================================================
"""

from __future__ import annotations

import time
from pathlib import Path

from app.core.logging import configure_logging
from app.schemas.image_preprocessing import (
    ImagePreprocessingRequest,
    ImagePreprocessingResponse,
    PipelineExecutionSummary,
    PreprocessingStageResult,
    ProcessingStatistics,
)
from app.services.image_processing_service import ImageProcessingService
from app.services.preprocessing_service import VisionPreprocessingService
from app.utils.image_enhancement import ImageEnhancement


class VisionPreprocessingExecutor:
    """
    Executes the complete preprocessing pipeline.

    The executor coordinates image loading, enhancement,
    preprocessing stage execution, timing, logging and
    response generation.
    """

    def __init__(self) -> None:

        self.logger = configure_logging()

        self.image_service = ImageProcessingService()

        self.preprocessing_service = VisionPreprocessingService()

        self.logger.info(
            "VisionPreprocessingExecutor initialized."
        )

    def execute(
        self,
        request: ImagePreprocessingRequest
    ) -> ImagePreprocessingResponse:
        """
        Execute the preprocessing pipeline.

        Parameters
        ----------
        request
            Image preprocessing request.

        Returns
        -------
        ImagePreprocessingResponse
        """

        pipeline_start = time.perf_counter()

        stage_results: list[PreprocessingStageResult] = []

        failed_stages = 0

        image = self.image_service.load_image(
            request.filename
        )

        #
        # Built-in enhancement stages
        #

        built_in_stages = [
            (
                "brightness_normalization",
                request.apply_brightness,
                lambda img: ImageEnhancement.normalize_brightness(img),
            ),
            (
                "contrast_enhancement",
                request.apply_contrast,
                lambda img: ImageEnhancement.enhance_contrast(img),
            ),
            (
                "grayscale_conversion",
                request.apply_grayscale,
                lambda img: ImageEnhancement.convert_to_grayscale(img),
            ),
            (
                "resize",
                request.resize_width is not None
                or request.resize_height is not None,
                lambda img: ImageEnhancement.resize_image(
                    img,
                    width=request.resize_width,
                    height=request.resize_height,
                ),
            ),
        ]

        for stage_name, enabled, operation in built_in_stages:

            if not enabled:
                continue

            stage_start = time.perf_counter()

            try:

                self.logger.info(
                    "Executing stage: %s",
                    stage_name,
                )

                image = operation(image)

                stage_results.append(
                    PreprocessingStageResult(
                        stage_name=stage_name,
                        executed=True,
                        success=True,
                        execution_time_ms=(
                            time.perf_counter() - stage_start
                        ) * 1000,
                        message="Completed",
                    )
                )

            except Exception as exc:

                failed_stages += 1

                self.logger.exception(
                    "Stage failed: %s",
                    stage_name,
                )

                stage_results.append(
                    PreprocessingStageResult(
                        stage_name=stage_name,
                        executed=True,
                        success=False,
                        execution_time_ms=(
                            time.perf_counter() - stage_start
                        ) * 1000,
                        message=str(exc),
                    )
                )

        #
        # Registered preprocessing stages
        #

        for stage_name in self.preprocessing_service.registered_stages():

            stage_results.append(
                PreprocessingStageResult(
                    stage_name=stage_name,
                    executed=True,
                    success=True,
                    execution_time_ms=0.0,
                    message="Registered stage",
                )
            )

        info = self.image_service.image_information(image)

        file_size = None

        try:
            # Mirror the same filename-only, base-directory-constrained
            # resolution used by ImageProcessingService.load_image, so
            # this stat() call can't be used to probe arbitrary paths.
            safe_path = Path("uploads").resolve() / Path(request.filename).name
            file_size = safe_path.stat().st_size
        except Exception:
            pass

        statistics = ProcessingStatistics(
            width=info["width"],
            height=info["height"],
            channels=info["channels"],
            file_size_bytes=file_size,
            color_space=(
                "GRAY"
                if info["channels"] == 1
                else "BGR"
            ),
        )

        summary = PipelineExecutionSummary(
            total_stages=len(stage_results),
            successful_stages=(
                len(stage_results) - failed_stages
            ),
            failed_stages=failed_stages,
            total_execution_time_ms=(
                time.perf_counter() - pipeline_start
            )
            * 1000,
        )

        return ImagePreprocessingResponse(
            status=(
                "success"
                if failed_stages == 0
                else "partial_success"
            ),
            filename=request.filename,
            processed_filename=request.filename,
            statistics=statistics,
            stages=stage_results,
            summary=summary,
        )
