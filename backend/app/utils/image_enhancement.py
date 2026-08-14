"""
====================================================================
Project : AEGIS
System  : Autonomous Enterprise Global Intelligence System
Company : Honeydewnuts Nigerian Limited

File    : image_enhancement.py

Purpose :
Image enhancement utilities used by the Vision Preprocessing Engine.

This module contains reusable OpenCV-based image enhancement
operations that prepare trading screenshots for downstream
computer vision modules.

Current Stage:
CP-003 Part 1 – Batch 3

Future Consumers:

    • Chart Detection Engine
    • Candlestick Recognition Engine
    • Indicator Recognition Engine
    • OCR Engine
    • Trading Intelligence Engine

NOTE: VisionPreprocessingService and VisionPipelineService were removed
as dead code (implemented but never wired to anything) - see git history
around the point this note was added. If you're building either for
real, this module is still a reasonable place to draw enhancement
utilities from.

====================================================================
"""

from __future__ import annotations

import logging

import cv2
import numpy as np


logger = logging.getLogger(__name__)


class ImageEnhancement:
    """
    Collection of reusable image enhancement operations.

    Every method returns a new processed image and does not
    modify the original image in-place.
    """

    @staticmethod
    def normalize_brightness(
        image: np.ndarray,
        beta: float = 15.0
    ) -> np.ndarray:
        """
        Apply brightness normalization.

        Parameters
        ----------
        image:
            Input OpenCV image.

        beta:
            Brightness adjustment.

        Returns
        -------
        numpy.ndarray
        """

        logger.debug("Applying brightness normalization.")

        return cv2.convertScaleAbs(
            image,
            alpha=1.0,
            beta=beta
        )

    @staticmethod
    def enhance_contrast(
        image: np.ndarray,
        alpha: float = 1.25
    ) -> np.ndarray:
        """
        Enhance image contrast.

        Parameters
        ----------
        alpha:
            Contrast multiplier.
        """

        logger.debug("Applying contrast enhancement.")

        return cv2.convertScaleAbs(
            image,
            alpha=alpha,
            beta=0
        )

    @staticmethod
    def convert_to_grayscale(
        image: np.ndarray
    ) -> np.ndarray:
        """
        Convert image to grayscale.

        If already grayscale,
        the original image is returned.
        """

        logger.debug("Converting image to grayscale.")

        if len(image.shape) == 2:
            return image

        return cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY
        )

    @staticmethod
    def resize_image(
        image: np.ndarray,
        width: int | None = None,
        height: int | None = None,
        interpolation: int = cv2.INTER_AREA
    ) -> np.ndarray:
        """
        Resize an image.

        Aspect ratio is preserved if only one
        dimension is supplied.
        """

        logger.debug("Resizing image.")

        if width is None and height is None:
            return image

        original_height, original_width = image.shape[:2]

        if width is None:

            ratio = height / float(original_height)

            width = int(original_width * ratio)

        elif height is None:

            ratio = width / float(original_width)

            height = int(original_height * ratio)

        return cv2.resize(
            image,
            (width, height),
            interpolation=interpolation
        )

    @staticmethod
    def gaussian_blur(
        image: np.ndarray,
        kernel_size: tuple[int, int] = (5, 5)
    ) -> np.ndarray:
        """
        Apply Gaussian blur.

        Useful for reducing image noise.
        """

        logger.debug("Applying Gaussian blur.")

        return cv2.GaussianBlur(
            image,
            kernel_size,
            0
        )

    @staticmethod
    def sharpen(
        image: np.ndarray
    ) -> np.ndarray:
        """
        Apply sharpening filter.
        """

        logger.debug("Applying sharpening filter.")

        kernel = np.array([
            [0, -1, 0],
            [-1, 5, -1],
            [0, -1, 0]
        ])

        return cv2.filter2D(
            image,
            -1,
            kernel
        )

    @staticmethod
    def histogram_equalization(
        image: np.ndarray
    ) -> np.ndarray:
        """
        Improve grayscale contrast using histogram equalization.

        Colour images are internally converted
        to grayscale.
        """

        logger.debug(
            "Applying histogram equalization."
        )

        gray = ImageEnhancement.convert_to_grayscale(
            image
        )

        return cv2.equalizeHist(gray)
