"""
Project: AEGIS
Company: Honeydewnuts Nigerian Limited

Purpose:
Basic image loading and inspection service.
"""

from pathlib import Path

import cv2

# All image reads are constrained to this directory. Every router that
# accepts a path/filename from a client (upload_router, chart_detection_router,
# preprocessing_router) ultimately calls load_image(), so enforcing the
# boundary here closes the path-traversal hole in one place rather than
# needing every caller to remember to sanitize input themselves.
ALLOWED_BASE_DIRECTORY = Path("uploads").resolve()


class ImageProcessingService:

    def load_image(self, image_path: str):

        # Treat the input as a filename within ALLOWED_BASE_DIRECTORY,
        # not as an arbitrary path. This blocks "../../etc/passwd" style
        # traversal even if the caller passes a path with directory
        # components - only the final filename component is honored.
        requested_name = Path(image_path).name
        path = (ALLOWED_BASE_DIRECTORY / requested_name).resolve()

        if not str(path).startswith(str(ALLOWED_BASE_DIRECTORY)):
            raise ValueError("Invalid image path.")

        if not path.exists():
            raise FileNotFoundError(
                f"Image not found: {image_path}"
            )

        image = cv2.imread(str(path))

        if image is None:
            raise ValueError(
                "Unable to read image."
            )

        return image

    def image_information(self, image):

        height, width = image.shape[:2]

        channels = 1 if len(image.shape) == 2 else image.shape[2]

        return {
            "width": width,
            "height": height,
            "channels": channels
        }
