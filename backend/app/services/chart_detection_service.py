"""
====================================================================
Project : AEGIS
System  : Autonomous Enterprise Global Intelligence System
Company : Honeydewnuts Nigerian Limited

File    : chart_detection_service.py

Purpose :
Chart Detection Service.

Locates the chart region within a preprocessed trading screenshot
and prepares structured data for downstream computer vision modules.

Current Stage:
CP-004 – Batch 1

Responsibilities

• Load preprocessed image
• Determine image dimensions
• Detect chart boundaries
• Detect plotting area
• Prepare metadata for Candlestick Recognition Engine

This service deliberately does NOT perform candlestick recognition.
====================================================================
"""

from __future__ import annotations

from typing import Any

from app.core.logging import configure_logging
from app.services.image_processing_service import ImageProcessingService


class ChartDetectionService:
    """
    Detects the primary chart region.

    The initial implementation uses configurable margins to define
    the chart area. Future batches will replace this with OpenCV-
    based contour and edge detection while preserving the public API.
    """

    def __init__(self) -> None:

        self.logger = configure_logging()

        self.image_service = ImageProcessingService()

        self.logger.info(
            "ChartDetectionService initialized."
        )

    def detect(
        self,
        image_path: str
    ) -> dict[str, Any]:
        """
        Detect the chart region.

        Parameters
        ----------
        image_path
            Path to a preprocessed image.

        Returns
        -------
        dict
            Structured chart detection result.
        """

        self.logger.info(
            "Loading image for chart detection: %s",
            image_path,
        )

        image = self.image_service.load_image(image_path)

        info = self.image_service.image_information(image)

        width = info["width"]
        height = info["height"]

        #
        # Conservative margins.
        # These can later be replaced by automatic
        # OpenCV detection.
        #

        left = int(width * 0.05)
        right = int(width * 0.95)

        top = int(height * 0.10)
        bottom = int(height * 0.90)

        plotting_area = {
            "x": left,
            "y": top,
            "width": right - left,
            "height": bottom - top,
        }

        result = {
            "status": "success",

            "image": {
                "width": width,
                "height": height,
                "channels": info["channels"],
            },

            "chart_region": {
                "left": left,
                "right": right,
                "top": top,
                "bottom": bottom,
            },

            "plotting_area": plotting_area,

            "candlestick_input": {
                "image_path": image_path,
                "plotting_area": plotting_area,
            },
        }

        self.logger.info(
            "Chart region detected successfully."
        )

        return result
