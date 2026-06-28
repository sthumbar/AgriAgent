"""Image processing utilities for the Agri AI Assistant."""

import base64
import io
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_MAX_SIZE: Tuple[int, int] = (1024, 1024)


class ImageProcessingError(Exception):
    """Raised when image validation or processing fails."""


def validate_image_extension(image_path: str) -> None:
    """Raise ImageProcessingError if the file extension is not supported."""
    suffix = Path(image_path).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ImageProcessingError(
            f"Unsupported image format '{suffix}'. "
            f"Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )


def get_mime_type(image_path: str) -> str:
    """Return the MIME type for the given image path."""
    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
    }
    suffix = Path(image_path).suffix.lower()
    return mapping.get(suffix, "image/jpeg")


def resize_image(image: Image.Image, max_size: Tuple[int, int] = DEFAULT_MAX_SIZE) -> Image.Image:
    """
    Resize image to fit within max_size while preserving aspect ratio.

    Uses LANCZOS resampling for high quality downscaling.
    """
    if image.size[0] <= max_size[0] and image.size[1] <= max_size[1]:
        return image

    image.thumbnail(max_size, Image.LANCZOS)
    logger.debug("Image resized to %s", image.size)
    return image


def convert_to_rgb(image: Image.Image) -> Image.Image:
    """Convert image to RGB mode if necessary (handles RGBA, P, etc.)."""
    if image.mode not in ("RGB", "L"):
        return image.convert("RGB")
    return image


def load_and_process_image(
    image_path: str,
    max_size: Tuple[int, int] = DEFAULT_MAX_SIZE,
) -> Dict[str, str]:
    """
    Validate, load, resize, and encode an image for the Gemini Vision API.

    Args:
        image_path: Absolute or relative path to the image file.
        max_size: Maximum (width, height) after resizing.

    Returns:
        Dict with keys:
          - ``base64_data``: Base64-encoded JPEG bytes.
          - ``mime_type``: MIME type string (e.g. ``"image/jpeg"``).
          - ``original_size``: ``"WxH"`` of the original image.
          - ``processed_size``: ``"WxH"`` after resize.

    Raises:
        ImageProcessingError: On validation or processing failure.
        FileNotFoundError: If the image file does not exist.
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    validate_image_extension(image_path)

    try:
        with Image.open(path) as img:
            original_size = f"{img.width}x{img.height}"
            img = convert_to_rgb(img)
            img = resize_image(img, max_size)
            processed_size = f"{img.width}x{img.height}"

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=90)
            buffer.seek(0)
            encoded = base64.b64encode(buffer.read()).decode("utf-8")

        logger.info(
            "Image processed: %s → original=%s, processed=%s",
            path.name,
            original_size,
            processed_size,
        )

        return {
            "base64_data": encoded,
            "mime_type": "image/jpeg",
            "original_size": original_size,
            "processed_size": processed_size,
        }

    except (OSError, ValueError) as exc:
        raise ImageProcessingError(f"Failed to process image '{image_path}': {exc}") from exc


def get_pil_image(image_path: str, max_size: Tuple[int, int] = DEFAULT_MAX_SIZE) -> Image.Image:
    """
    Return a processed PIL Image object.

    Useful for display in Streamlit (``st.image``).
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    validate_image_extension(image_path)

    with Image.open(path) as img:
        img = convert_to_rgb(img)
        img = resize_image(img, max_size)
        return img.copy()


def save_uploaded_image(file_bytes: bytes, filename: str, dest_dir: str) -> str:
    """
    Save uploaded bytes to dest_dir, returning the full saved path.

    Validates the extension before saving.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    validate_image_extension(filename)

    save_path = dest / filename
    save_path.write_bytes(file_bytes)
    logger.info("Uploaded image saved to %s", save_path)
    return str(save_path)
